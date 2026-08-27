from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register mappings)

    Base.metadata.create_all(engine)
    _migrate()


# columns added after a table first shipped; create_all won't add them to existing DBs
_COLUMN_MIGRATIONS = [
    ("decision", "review_on", "DATE"),
    ("topic", "recurring", "BOOLEAN DEFAULT 0"),
    ("workstream", "sort_order", "INTEGER DEFAULT 0"),
]

# Single-person columns that became many-to-many join tables. The old column is
# left in the SQLite file — dropping one is awkward there, and keeping it is a
# rollback path — but it is gone from the ORM models, so after this backfill the
# join table is the only thing anything reads.
#   (parent table, legacy column, join table, parent fk, person fk)
_ASSOCIATION_BACKFILLS = [
    ("workstream", "owner_id", "workstream_owner", "workstream_id", "person_id"),
    ("topic", "sponsor_id", "topic_sponsor", "topic_id", "person_id"),
]


def _migrate() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        if table not in tables:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column not in existing:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))

    for parent, legacy, join, parent_fk, person_fk in _ASSOCIATION_BACKFILLS:
        # A database created fresh by create_all never had the legacy column, so
        # there is nothing to carry over. An existing one is copied exactly once:
        # a non-empty join table means the backfill has already run (or the user
        # has since edited the owners by hand, which must not be overwritten).
        if parent not in tables or join not in tables:
            continue
        if legacy not in {col["name"] for col in inspector.get_columns(parent)}:
            continue
        with engine.begin() as connection:
            if connection.execute(text(f"SELECT 1 FROM {join} LIMIT 1")).first():
                continue
            connection.execute(
                text(
                    f"INSERT OR IGNORE INTO {join} ({parent_fk}, {person_fk}) "
                    f"SELECT id, {legacy} FROM {parent} WHERE {legacy} IS NOT NULL"
                )
            )
