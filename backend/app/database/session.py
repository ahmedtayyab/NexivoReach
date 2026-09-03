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
    additions = [
        ("productitem", "user_id", "VARCHAR"),
        ("productitem", "source_url", "VARCHAR"),
        ("productitem", "in_stock", "BOOLEAN"),
        ("prospectrecord", "user_id", "VARCHAR"),
        ("agentrunrecord", "user_id", "VARCHAR"),
    ]
    with engine.connect() as conn:
        for table, column, coltype in additions:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                conn.commit()
            except Exception:
                conn.rollback()


def get_session():
    with Session(engine) as session:
        yield session
