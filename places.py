# places.py

from datetime import datetime, timedelta
from Database import get_db_session, Place, PlaceOccupancy

# Utility: Get a place by its ID
def get_place_by_id(place_id: str):
    with get_db_session() as session:
        return session.query(Place).filter_by(place_id=place_id).first()

# Utility: Check if a place is full
def is_place_full(place_id: str) -> bool:
    session = get_db_session()
    place = get_place_by_id(place_id)
    if not place or place.max_capacity is None:
        return False  # If no capacity is defined, the place is never full

    current = session.query(PlaceOccupancy).filter_by(place_id=place_id).count()
    session.close()
    return current >= place.max_capacity

# Vehicle tries to enter a place
def try_enter_place(vehicle_id: str, place_id: str) -> tuple[bool, str]:
    session = get_db_session()
    place = get_place_by_id(place_id)
    if not place:
        return False, "INVALID_PLACE"

    if place.pass_through:
        return True, "PASSTHROUGH"

    if is_place_full(place_id):
        return False, "FULL"

    leave_time = datetime.utcnow() + timedelta(seconds=place.stay_time_seconds or 60)
    entry = PlaceOccupancy(vehicle_id=vehicle_id, place_id=place_id, leave_after=leave_time)
    session.add(entry)
    session.commit()
    return True, "ENTERED"


# Get vehicles that should now leave (expired stay time)
def get_expired_occupants():
    session = get_db_session()
    return session.query(PlaceOccupancy).filter(PlaceOccupancy.leave_after <= datetime.utcnow()).all()


# Remove a vehicle from a place
def remove_vehicle_from_place(vehicle_id: str):
    session = get_db_session()
    occupancy = session.query(PlaceOccupancy).filter_by(vehicle_id=vehicle_id).first()
    if occupancy:
        session.delete(occupancy)
        session.commit()
        return True
    return False

# Optional: Debug list of all places
def list_all_places():
    session = get_db_session()
    places = session.query(Place).all()
    for p in places:
        print(f"[{p.place_id}] {p.name} | Type: {p.type} | Cap: {p.max_capacity} | Stay: {p.stay_time_seconds}s | PT: {p.pass_through}")
