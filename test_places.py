from places import (
    list_all_places,
    try_enter_place,
    is_place_full,
    get_expired_occupants,
    remove_vehicle_from_place
)
import time

def test_flow():
    print("\n📍 All places:")
    list_all_places()

    print("\n🚗 Entering Union Square Park (P001) with 5 vehicles:")
    for i in range(1, 6):
        vid = f"B10{i}"
        success, msg = try_enter_place(vid, "P001")
        print(f"{vid} → {msg}")

    print("\n❓ Is P001 full now?")
    print(is_place_full("P001"))  # Should now be True (capacity = 5)

    print("\n🚫 Trying to enter B106 (should fail due to full capacity):")
    success, msg = try_enter_place("B106", "P001")
    print(f"B106 → {msg}")  # Should be FULL

    print("\n🧍 Testing passthrough entry (B200 at P002):")
    success, msg = try_enter_place("B200", "P002")  # P002 is a pass-through
    print(f"B200 → {msg}")  # Should be PASSTHROUGH

    print("\n⏳ Waiting 2 seconds (simulate short stays)...")
    time.sleep(2)

    print("\n🔍 Checking for expired occupants (should be none with 120s stays):")
    expired = get_expired_occupants()
    print(f"Expired: {len(expired)} occupant(s)")
    for occ in expired:
        print(f"- {occ.vehicle_id} at {occ.place_id}, leave after {occ.leave_after}")

    print("\n🧹 Manually removing all 5 vehicles from P001:")
    for i in range(1, 6):
        vid = f"B10{i}"
        removed = remove_vehicle_from_place(vid)
        print(f"{vid} removed? {removed}")

    print("\n✅ Testing complete.")

if __name__ == "__main__":
    test_flow()
