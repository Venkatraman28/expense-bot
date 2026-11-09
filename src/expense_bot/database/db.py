from pathlib import Path
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from expense_bot.config import settings
from expense_bot.database.models import Base

DEFAULT_CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Transport",
    "Shopping",
    "Bills & Utilities",
    "Rent",
    "Health",
    "Entertainment",
    "Travel",
    "Education",
    "Subscriptions",
    "Personal Care",
    "Gifts & Donations",
    "Other",
]


def db_url(db_path: str) -> str:
    return URL.create("sqlite", database=db_path)


def make_engine(db_path: str) -> Engine:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db_url(db_path))

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = make_engine(settings.DB_PATH)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db(engine: Engine, user_ids: set[int]) -> None:
    """Create tables if they don't exists and seed default categories"""
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        for uid in user_ids:
            query = text("SELECT id FROM categories WHERE user_id = :user_id LIMIT 1")
            result = session.execute(query, {"user_id": uid}).first()

            if not result:
                insert_stmt = text(
                    """
                    INSERT INTO categories (user_id, name, is_custom, created_at)
                    VALUES (:user_id, :name, 0, CURRENT_TIMESTAMP)
                    """
                )
                for name in DEFAULT_CATEGORIES:
                    session.execute(
                        insert_stmt, 
                        {"user_id": uid, "name": name, "is_custom": False}
                    )
        
        session.commit()