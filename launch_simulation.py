import subprocess
import time
import random
from Database import get_db_session, Vehicle as VehicleModel, Routes

# Parameters
NUM_VEHICLES = 5
PLACE_IDS = ["P001", "P002", "P003", "P004", "P005", "P006", "P007", "P008", "P009", "P010"]
VEHICLE_TYPES = ["B", "U", "S", "T"]

session = get_db_session()
vehicles = []

print("Generating vehicles and assigning routes...")
for i in range(NUM_VEHICLES):
    vtype = random.choice(VEHICLE_TYPES)
    vid = f"{vtype}{100 + i}"
    vehicles.append(vid)

    existing = session.query(VehicleModel).filter_by(vehicle_id=vid).first()
    if not existing:
        session.add(VehicleModel(vehicle_id=vid, vehicle_type=vtype, status='IDLE'))

    # Assign fresh route
    session.query(Routes).filter_by(vehicle_id=vid).delete()
    route_length = random.randint(2, 5)
    stops = random.sample(PLACE_IDS, route_length)
    for step, place_id in enumerate(stops):
        session.add(Routes(vehicle_id=vid, step_index=step, place_id=place_id))

    print(f"{vid} assigned route: {stops}")

session.commit()
session.close()

print("Launching all vehicles...")
for vid in vehicles:
    subprocess.Popen(["python", "Vehicle.py", vid])
    time.sleep(0.5)
