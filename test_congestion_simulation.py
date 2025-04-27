import subprocess
import time
from Database import get_db_session, Vehicle as VehicleModel, Routes, Place

# Parameters
NUM_VEHICLES = 5  # Number of vehicles to simulate
PLACE_ID = "P001"  # Place with low capacity
PLACE_CAPACITY = 2  # Maximum number of vehicles allowed in the place at once
ROUTE_LENGTH = 3  # Number of stops in each route
VEHICLE_TYPES = ["B", "U", "S", "T"]

# Set up the database
session = get_db_session()

# Create the test place with low capacity
print(f"Setting up place {PLACE_ID} with capacity {PLACE_CAPACITY}...")
place = session.query(Place).filter_by(place_id=PLACE_ID).first()
if not place:
    place = Place(
        place_id=PLACE_ID,
        name="Test Place",
        type="Test",
        latitude=40.0,
        longitude=-73.0,
        max_capacity=PLACE_CAPACITY,
        stay_time_seconds=10,  # Vehicles will stay for 10 seconds
    )
    session.add(place)
else:
    place.max_capacity = PLACE_CAPACITY
    place.stay_time_seconds = 10

# Generate vehicles and assign routes
vehicles = []
print("Generating vehicles and assigning routes...")
for i in range(NUM_VEHICLES):
    vtype = VEHICLE_TYPES[i % len(VEHICLE_TYPES)]
    vid = f"{vtype}{100 + i}"
    vehicles.append(vid)

    # Add vehicle to the database if it doesn't exist
    existing = session.query(VehicleModel).filter_by(vehicle_id=vid).first()
    if not existing:
        session.add(VehicleModel(vehicle_id=vid, vehicle_type=vtype, status='IDLE'))

    # Assign a route that includes the test place
    session.query(Routes).filter_by(vehicle_id=vid).delete()  # Clear existing routes
    route = [PLACE_ID] + [f"P00{i+2}" for i in range(ROUTE_LENGTH - 1)]  # Route starts with PLACE_ID
    for step, place_id in enumerate(route):
        session.add(Routes(vehicle_id=vid, step_index=step, place_id=place_id))

    print(f"{vid} assigned route: {route}")

# Commit changes to the database
session.commit()
session.close()

# Launch vehicles
print("Launching vehicles...")
for vid in vehicles:
    subprocess.Popen(["python", "Vehicle.py", vid])
    time.sleep(0.5)  # Slight delay between launches to simulate staggered starts

# Monitor the simulation
print("Simulation started. Monitor the logs to observe congestion behavior.")
print("Vehicles should wait their turn to enter the place if it is full.")