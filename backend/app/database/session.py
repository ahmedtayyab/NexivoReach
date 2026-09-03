from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)


def init_db():
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_columns()
    _migrate_multi_company()


def _ensure_sqlite_columns():
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(productitem)")).fetchall()}
        if "specs" in cols or "ai_extracted" in cols:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS productitem_new (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    category VARCHAR NOT NULL,
                    description VARCHAR NOT NULL,
                    price VARCHAR, moq VARCHAR,
                    product_url VARCHAR, image_url VARCHAR,
                    source_url VARCHAR, in_stock BOOLEAN,
                    user_id VARCHAR, business_id VARCHAR
                )
            """))
            conn.execute(text("""
                INSERT INTO productitem_new
                    (id, name, category, description, price, moq, product_url, image_url, source_url, in_stock, user_id, business_id)
                SELECT id, name, category, description, price, moq, product_url, image_url, source_url, in_stock, user_id, NULL
                FROM productitem
            """))
            conn.execute(text("DROP TABLE productitem"))
            conn.execute(text("ALTER TABLE productitem_new RENAME TO productitem"))
            conn.commit()

        additions = [
            ("business", "user_id", "VARCHAR"),
            ("business", "updated_at", "VARCHAR"),
            ("productitem", "source_url", "VARCHAR"),
            ("productitem", "in_stock", "BOOLEAN"),
            ("productitem", "business_id", "VARCHAR"),
            ("icpconfig", "business_id", "VARCHAR"),
            ("prospectrecord", "user_id", "VARCHAR"),
            ("prospectrecord", "business_id", "VARCHAR"),
            ("prospectrecord", "source", "VARCHAR"),
            ("prospectrecord", "phone", "VARCHAR"),
            ("agentrunrecord", "user_id", "VARCHAR"),
            ("agentrunrecord", "business_id", "VARCHAR"),
            ("user", "active_business_id", "VARCHAR"),
        ]
        for table, column, coltype in additions:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                conn.commit()
            except Exception:
                conn.rollback()


def _migrate_multi_company():
    """Backfill user_id / business_id for the old 1-user-1-company layout."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        try:
            # Old Business rows used id == user.id and had no user_id
            conn.execute(text("""
                UPDATE business
                SET user_id = id
                WHERE user_id IS NULL OR user_id = ''
            """))
            conn.execute(text("""
                UPDATE icpconfig
                SET business_id = id
                WHERE business_id IS NULL OR business_id = ''
            """))
            # Products previously scoped by user_id (== old business id)
            conn.execute(text("""
                UPDATE productitem
                SET business_id = user_id
                WHERE (business_id IS NULL OR business_id = '')
                  AND user_id IS NOT NULL AND user_id != ''
            """))
            conn.execute(text("""
                UPDATE prospectrecord
                SET business_id = user_id
                WHERE (business_id IS NULL OR business_id = '')
                  AND user_id IS NOT NULL AND user_id != ''
            """))
            conn.execute(text("""
                UPDATE agentrunrecord
                SET business_id = user_id
                WHERE (business_id IS NULL OR business_id = '')
                  AND user_id IS NOT NULL AND user_id != ''
            """))
            # Set active company for users who already have a business
            conn.execute(text("""
                UPDATE user
                SET active_business_id = (
                    SELECT b.id FROM business b
                    WHERE b.user_id = user.id
                    ORDER BY b.updated_at DESC, b.name ASC
                    LIMIT 1
                )
                WHERE active_business_id IS NULL OR active_business_id = ''
            """))
            conn.commit()
        except Exception:
            conn.rollback()


def get_session():
    with Session(engine) as session:
        yield session
