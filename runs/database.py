import os
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
DEFAULT_DATABASE = f"sqlite:///{(PROJECT_ROOT / 'output/testgen.db').as_posix()}"


class Base(DeclarativeBase):
    pass


def database_url():
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE)


def make_engine(url=None):
    url = url or database_url()
    if url.startswith("sqlite"):
        (PROJECT_ROOT / "output").mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_database():
    from runs.models import GenerationRun  # noqa: F401
    if engine.dialect.name == "postgresql":
        # API and worker can start together; serialize this minimal schema bootstrap.
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(84117623)"))
            Base.metadata.create_all(connection)
    else:
        Base.metadata.create_all(engine)
