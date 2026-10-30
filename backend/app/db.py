"""Engine and session factory: SQLite for local work, Postgres when DATABASE_URL points at one."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.tables import Base


def normalise_url(url: str) -> str:
    """Render hands out postgres:// URLs; SQLAlchemy with psycopg 3 wants postgresql+psycopg://."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


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
    Base.metadata.create_all(engine)  # fine for the first deploy; move to migrations before the schema changes in production
    return sessionmaker(engine, expire_on_commit=False)
