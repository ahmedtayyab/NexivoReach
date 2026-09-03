from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)


def init_db():
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_columns()


def _ensure_sqlite_columns():
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        # Rebuild productitem if it still has the old NOT NULL columns (specs/features/ai_extracted/verified_by_user)
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
                    source_url VARCHAR, in_stock BOOLEAN, user_id VARCHAR
                )
            """))
            conn.execute(text("""
                INSERT INTO productitem_new
                    (id, name, category, description, price, moq, product_url, image_url, source_url, in_stock, user_id)
                SELECT id, name, category, description, price, moq, product_url, image_url, source_url, in_stock, user_id
                FROM productitem
            """))
            conn.execute(text("DROP TABLE productitem"))
            conn.execute(text("ALTER TABLE productitem_new RENAME TO productitem"))
            conn.commit()

        # Additive migrations for other tables
        additions = [
            ("productitem", "source_url", "VARCHAR"),
            ("productitem", "in_stock", "BOOLEAN"),
            ("prospectrecord", "user_id", "VARCHAR"),
            ("agentrunrecord", "user_id", "VARCHAR"),
        ]
        for table, column, coltype in additions:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                conn.commit()
            except Exception:
                conn.rollback()


def get_session():
    with Session(engine) as session:
        yield session
