from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import uuid
import logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Define the base class for models
Base = declarative_base()

# Define the database URL
DB_URL = "sqlite:///instance/main.db"

# Create a single engine instance (thread-safe)
engine = create_engine(DB_URL, echo=False)

# Create a configured "Session" class
SessionLocal = sessionmaker(bind=engine)

# Models
class Vehicle(Base):
    __tablename__ = 'vehicles'
    vehicle_id = Column(String, primary_key=True)
    vehicle_type = Column(String, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
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
    
class Place(Base):
    __tablename__ = 'places'
    place_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    max_capacity = Column(Integer, nullable=True)
    stay_time_seconds = Column(Integer, nullable=True)
    pass_through = Column(Boolean, default=False, nullable=False)

    occupants = relationship("PlaceOccupancy", backref="place")

    def __repr__(self):
        return f"<Place(id={self.place_id}, name='{self.name}', type='{self.type}')>"


class PlaceOccupancy(Base):
    __tablename__ = 'place_occupancy'

    occupancy_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vehicle_id = Column(String, nullable=False)  # e.g., "B101"
    place_id = Column(String, ForeignKey('places.place_id'), nullable=False)
    entered_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    leave_after = Column(DateTime, nullable=False)

    def __repr__(self):
        return f"<Occupancy(vehicle={self.vehicle_id}, place={self.place_id}, leave_after={self.leave_after})>"
    
class Routes(Base):
    __tablename__ = 'routes'

    vehicle_id = Column(String, primary_key=True)
    step_index = Column(Integer, primary_key=True)  # 0, 1, 2, ...
    place_id = Column(String, ForeignKey("places.place_id"), nullable=False)

    def __repr__(self):
        return f"<RouteStep(vehicle={self.vehicle_id}, step={self.step_index}, place={self.place_id})>"

# Initialize the database
def init_db():
    Base.metadata.create_all(engine)

# Utility function to get a new session
def get_db_session():
    return SessionLocal()