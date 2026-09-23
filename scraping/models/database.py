"""Database setup and session management."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    """Create all tables and add columns introduced after a table was created.

    Models are imported via models/__init__.py.
    """
    Base.metadata.create_all(bind=engine)
    _add_missing_columns(engine)


def _add_missing_columns(bind):
    """``create_all`` never alters existing tables, so add new nullable columns here."""
    inspector = inspect(bind)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            if not column.nullable:
                raise RuntimeError(f"Cannot auto-add NOT NULL column {table.name}.{column.name}")
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(bind.dialect)}"
            with bind.begin() as conn:
                conn.execute(text(ddl))


if __name__ == "__main__":
    # Import models so they register with Base metadata
    from models import Product, Store, StoreLocation, Price, UserList, ListItem, ScrapeAttempt  # noqa: F401
    init_db()
    print("Database initialized.")
