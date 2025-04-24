from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime

# Define the base class for models
Base = declarative_base()

# Define the database URL
DB_URL = "sqlite:///instance/main.db"

# Create a single engine instance (thread-safe)
engine = create_engine(DB_URL, echo=True)

# Create a configured "Session" class
SessionLocal = sessionmaker(bind=engine)

# Models
class Vehicle(Base):
    __tablename__ = 'vehicles'
    vehicle_id = Column(String, primary_key=True)
    vehicle_password = Column(String, nullable=False)
    vehicle_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="IDLE")

class Session(Base):
    __tablename__ = 'sessions'
    session_id = Column(String, primary_key=True)
    vehicle_id = Column(String, ForeignKey('vehicles.vehicle_id'), nullable=False)
    expires_at = Column(DateTime, nullable=False)

class Location(Base):
    __tablename__ = 'locations'
    location_id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(String, ForeignKey('vehicles.vehicle_id'), nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Initialize the database
def init_db():
    Base.metadata.create_all(engine)

# Utility function to get a new session
def get_db_session():
    return SessionLocal()