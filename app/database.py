# orders_service/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

POSTGRES_USER = os.getenv("ORDERS_DB_USER", "orders_user")
POSTGRES_PASSWORD = os.getenv("ORDERS_DB_PASSWORD", "orders_pass")
POSTGRES_DB = os.getenv("ORDERS_DB_NAME", "orders_db")
POSTGRES_HOST = os.getenv("ORDERS_DB_HOST", "postgres")
POSTGRES_PORT = os.getenv("ORDERS_DB_PORT", "5432")

DATABASE_URL = os.getenv("DATABASE_URL") or (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
