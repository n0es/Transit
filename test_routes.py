from Database import get_db_session, Routes

def test_routes(vehicle_id: str):
    session = get_db_session()
    steps = session.query(Routes).filter_by(vehicle_id=vehicle_id).order_by(Routes.step_index).all()

    print(f"📍 Route for {vehicle_id}:")
    for step in steps:
        print(f"Step {step.step_index}: {step.place_id}")

if __name__ == "__main__":
    test_routes("B101")
    test_routes("B102")
