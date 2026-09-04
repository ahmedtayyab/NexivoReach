from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from app.config import database_backend, settings

_backend = database_backend()
_connect_args = {"check_same_thread": False} if _backend == "sqlite" else {}
_engine_kwargs = {"echo": False, "connect_args": _connect_args}
if _backend == "postgres":
    _engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    })

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)


def init_db():
    # SQLite-only legacy patches before create_all so renamed tables are ready.
    if _backend == "sqlite":
        _migrate_sqlite_user_table()
    SQLModel.metadata.create_all(engine)
    _ensure_prospect_contact_columns()
    if _backend == "sqlite":
        _ensure_sqlite_columns()
        _migrate_multi_company()


def _ensure_prospect_contact_columns():
    """Add outreach/contact columns on existing DBs (SQLite + Postgres)."""
    additions = [
        ("prospectrecord", "email", "VARCHAR"),
        ("prospectrecord", "contacts", "JSON" if _backend == "postgres" else "TEXT"),
        ("prospectrecord", "contact_again", "BOOLEAN"),
        ("prospectrecord", "last_reply_at", "VARCHAR"),
        ("prospectrecord", "reply_summary", "VARCHAR"),
    ]
    with engine.connect() as conn:
        for table, column, coltype in additions:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                conn.commit()
            except Exception:
                conn.rollback()


def _migrate_sqlite_user_table():
    """Rename legacy SQLite table `user` → `nr_user` (Postgres-safe name)."""
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "user" in tables and "nr_user" not in tables:
            try:
                conn.execute(text('ALTER TABLE "user" RENAME TO nr_user'))
                conn.commit()
            except Exception:
                conn.rollback()


def _ensure_sqlite_columns():
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
            ("prospectrecord", "why_now", "VARCHAR"),
            ("agentrunrecord", "user_id", "VARCHAR"),
            ("agentrunrecord", "business_id", "VARCHAR"),
            ("nr_user", "active_business_id", "VARCHAR"),
            ("user", "active_business_id", "VARCHAR"),
        ]
        for table, column, coltype in additions:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                conn.commit()
            except Exception:
                conn.rollback()


def _migrate_multi_company():
    """Backfill user_id / business_id for the old 1-user-1-company layout (SQLite only)."""
    with engine.connect() as conn:
        try:
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
            conn.execute(text("""
                UPDATE nr_user
                SET active_business_id = (
                    SELECT b.id FROM business b
                    WHERE b.user_id = nr_user.id
                    ORDER BY b.updated_at DESC, b.name ASC
                    LIMIT 1
                )
                WHERE active_business_id IS NULL OR active_business_id = ''
            """))
            conn.commit()
        except Exception:
            conn.rollback()
            try:
                conn.execute(text("""
                    UPDATE "user"
                    SET active_business_id = (
                        SELECT b.id FROM business b
                        WHERE b.user_id = "user".id
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
