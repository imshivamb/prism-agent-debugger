from collections.abc import Generator
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
DATABASE_URL = f"sqlite:///{DATA_DIRECTORY / 'prism.db'}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def create_database() -> None:
    """Create the local database and its tables on first application start."""
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    from . import models  # noqa: F401 - register declarative models
    Base.metadata.create_all(bind=engine)
    # SQLite has no general ALTER COLUMN support. Keep the two protocol columns
    # forward-compatible for databases created before the provider architecture.
    existing_columns = {column["name"] for column in inspect(engine).get_columns("runs")}
    with engine.begin() as connection:
        if "trace_version" not in existing_columns:
            connection.execute(text("ALTER TABLE runs ADD COLUMN trace_version VARCHAR(16) NOT NULL DEFAULT '1.0'"))
        if "provider" not in existing_columns:
            connection.execute(text("ALTER TABLE runs ADD COLUMN provider VARCHAR(64) NOT NULL DEFAULT 'import'"))


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
