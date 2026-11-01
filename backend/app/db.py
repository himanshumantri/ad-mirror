"""Engine and session factory: SQLite for local work, Postgres when DATABASE_URL points at one."""
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.tables import Base


def normalise_url(url: str) -> str:
    """Render hands out postgres:// URLs; SQLAlchemy with psycopg 3 wants postgresql+psycopg://."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def add_missing_columns(engine) -> None:
    """Stopgap until real migrations: create_all never alters an existing table, so add any nullable column the
    code has gained since the table was created. Non-nullable additions need a proper migration."""
    existing = inspect(engine)
    for table in Base.metadata.sorted_tables:
        have = {c["name"] for c in existing.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                if not col.nullable:
                    raise RuntimeError(f"{table.name}.{col.name} is new and not nullable: write a migration")
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'))


def make_session_factory(url: str) -> sessionmaker[Session]:
    url = normalise_url(url)
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}  # background jobs open their own sessions on other threads
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # one shared in-memory database, for tests
        else:
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    return sessionmaker(engine, expire_on_commit=False)
