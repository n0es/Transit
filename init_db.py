# filepath: c:\Github\Transit\init_db.py
from Database import get_db_session, Place, init_db, Routes

def seed_places():
    session = get_db_session()

    # Check if places already exist
    existing = session.query(Place).first()
    if existing:
        print("Places already seeded. Skipping.")
        return

    places = [
        Place(place_id="P001", name="Union Square Park", type="park", latitude=40.7359, longitude=-73.9911, max_capacity=5, stay_time_seconds=120, pass_through=False),
        Place(place_id="P002", name="Broadway & 14th St", type="intersection", latitude=40.7372, longitude=-73.9906, max_capacity=None, stay_time_seconds=None, pass_through=True),
        Place(place_id="P003", name="Pizza Bros", type="restaurant", latitude=40.7421, longitude=-73.9893, max_capacity=3, stay_time_seconds=180, pass_through=False),
        Place(place_id="P004", name="City Parking Lot A", type="parking", latitude=40.7405, longitude=-73.9881, max_capacity=4, stay_time_seconds=90, pass_through=False),
        Place(place_id="P005", name="Coffee Crib", type="cafe", latitude=40.7365, longitude=-73.9922, max_capacity=2, stay_time_seconds=150, pass_through=False),
        Place(place_id="P006", name="CodeHub Office", type="office", latitude=40.7414, longitude=-73.9899, max_capacity=10, stay_time_seconds=600, pass_through=False),
        Place(place_id="P007", name="5th Ave & 23rd St", type="intersection", latitude=40.7409, longitude=-73.9897, max_capacity=None, stay_time_seconds=None, pass_through=True),
        Place(place_id="P008", name="Eastside Dog Park", type="park", latitude=40.7322, longitude=-73.9835, max_capacity=6, stay_time_seconds=180, pass_through=False),
        Place(place_id="P009", name="Flatiron Plaza", type="plaza", latitude=40.7411, longitude=-73.9897, max_capacity=5, stay_time_seconds=150, pass_through=False),
        Place(place_id="P010", name="Grand Central Corner", type="intersection", latitude=40.7527, longitude=-73.9772, max_capacity=None, stay_time_seconds=None, pass_through=True),
    ]

    session.add_all(places)
    session.commit()
    print("Seeded 10 default places.")
    
def seed_routes():
    session = get_db_session()

    if session.query(Routes).first():
        print("Routes already exist. Skipping.")
        return

    routes = [
        Routes(vehicle_id="B101", step_index=0, place_id="P001"),
        Routes(vehicle_id="B101", step_index=1, place_id="P003"),
        Routes(vehicle_id="B101", step_index=2, place_id="P004"),

        Routes(vehicle_id="B102", step_index=0, place_id="P002"),
        Routes(vehicle_id="B102", step_index=1, place_id="P005"),
        Routes(vehicle_id="B102", step_index=2, place_id="P006"),
    ]

    session.add_all(routes)
    session.commit()
    print("Seeded routes for B101 and B102.")

if __name__ == "__main__":
    init_db()
    seed_places()
    seed_routes()
    print("Database initialized and places/routes seeded successfully.")