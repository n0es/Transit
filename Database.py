import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Define the base class for models
Base = declarative_base()

# Define the database URL
DB_URL = "sqlite:///instance/main.db"

# Create a single engine instance (thread-safe)
engine = create_engine(DB_URL, echo=True)

# Create a configured "Session" class
SessionLocal = sessionmaker(bind=engine)

def get_db_session():
    """
    Creates and returns a new SQLAlchemy session for the main.db database.
    Each call returns a new session instance.
    """
    return SessionLocal()

# Example usage:
# session = get_db_session()
# Use `session` to interact with the database