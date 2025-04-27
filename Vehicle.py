#Vehicle.py
from typing import Tuple, Dict
from enum import Enum
import threading
import socket
from Database import get_db_session, Routes
import time
from places import get_place_by_id, try_enter_place, remove_vehicle_from_place, is_place_full

class VehicleType(Enum):
    TRAIN = "T"
    BUS = "B"
    UBER = "U"
    SHUTTLE = "S"


class Vehicle:
    COMMANDS: Dict[str, bool] = {
        "REGISTER": False,
        "LOGIN": False,
        "UPDATE_LOCATION": True,
    }
    def __init__(self, id: str, type: VehicleType, addr: Tuple[str, int], password: str = None, session: str = None) -> None:
        self.is_running = False
        self.id = id
        self.password = password
        self.session = session
        self.type = type
        if self.id[0]!=type.value:
            raise ValueError(f"Vehicle ID must correlate with vehicle type!\nID = {self.id}\nType = {self.type.value}")
        self.client = None

        self.connect(addr)
        
        self.route = []  # List of place IDs in the route
        self.current_index = 0  # Current step in the route
        self.state = "IDLE"  # IDLE, MOVING, WAITING, DELAYED, FINISHED
        self.lat = 0.0  # Current latitude
        self.lon = 0.0  # Current longitude
        self.delayed = False  # Whether the vehicle is delayed

    def _log(self, msg: str) -> None:
        print(self.id + " | " + msg)

    def connect(self, address):
        try:
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect(address)
            self._log("Connection established!")
        except socket.error as e:
            self._log(f"Connection failed: {e}")
            self.client = None

    def send(self, command_payload: str) -> bool:
        if not self.client:
            self._log("Cannot send: Not connected.")
            return False
        msg = f"{self.id}/{command_payload}"
        try:
            self._log(f"Sending: {msg}")
            self.client.sendall(msg.encode())
            return True
        except socket.error as e:
            self._log(f"Error sending message: {e}")
            self.client = None
            self.is_running = False
            return False
        except Exception as e:
            self._log(f"Unexpected error sending message: {e}")
            self.client = None
            self.is_running = False
            return False

    def receive(self) -> str:
        if not self.client:
            self._log("Cannot receive: Not connected.")
            return ""
        try:
            data = self.client.recv(1024).decode()
            if not data:
                self._log("Receive failed: Connection closed by server.")
                self.client = None
                self.is_running = False
                return ""
            return data
        except socket.timeout:
            self._log(f"Receive timed out.")
            return ""
        except socket.error as e:
            self._log(f"Error receiving message: {e}")
            self.client = None
            self.is_running = False
            return ""
        except Exception as e:
            self._log(f"Unexpected error receiving message: {e}")
            self.client = None
            self.is_running = False
            return ""

    def close(self) -> None:
        self.is_running = False
        if self.client:
            try:
                self.client.close()
                self._log("Connection closed")
            except socket.error as e:
                self._log(f"Error closing connection: {e}")
            finally:
                 self.client = None
                 
    def run(self) -> None:
        if not self.client:
            self._log("Cannot run: Not connected.")
            return

        self.register()
        if not self.session:
            self._log("Startup failed: Could not establish session.")
            self.close()
            return

        self.load_route_from_db()
        if not self.route:
            self._log("No route found. Vehicle will remain idle.")
            return

        self._log(f"Starting at position: ({self.lat}, {self.lon})")
        threading.Thread(target=self.run_route_loop, daemon=True).start()

        self.is_running = True
        self.open()

    def register(self) -> None:
        register_cmd = "REGISTER"
        if self.password:
            register_cmd += f"/{self.password}"

        if not self.send(register_cmd): return
        self._log("Sent REGISTER command")

        response = self.receive()
        if not response:
            self._log("Registration failed: No response received")
            return

        parts = response.split('/')
        status = parts[0]

        if status == "EXISTS":
            self._log("Vehicle exists, attempting login...")
            self.login()
        elif status == self.id and len(parts) > 1:
            self.session = parts[1]
            self._log("Registration successful!")
            self._log(f"Using session {self.session}")
        else:
            self._log(f"Registration failed or unexpected response: {response}")
            if status == "ERROR" and len(parts) > 1:
                self._log(f"Server error message: {parts[1]}")

    def login(self) -> None:
        if not self.password: self.password = ""
        if not self.send(f"LOGIN/{self.password}"): return

        response = self.receive()
        if not response:
            self._log("Login failed: No response received")
            return

        parts = response.split('/')
        status = parts[0]

        if status == self.id and len(parts) > 1:
            self.session = parts[1]
            self._log("Login successful!")
            self._log(f"Using session {self.session}")
        else:
            if status == "UNREGISTERED" or status == "INVALID" or status == "ERROR":
                error_message = parts[1] if len(parts) > 1 else "No details"
                self._log(f"Login failed: {status} - {error_message}")
            else:
                self._log(f"Login failed: Unexpected response format '{response}'")
            self.session = None

    def open(self):
        self._log("Command line opened. Type commands or press Ctrl+C to exit.")
        try:
            while self.is_running and self.client:
                input_str = input(f"{self.id}> ").strip()
                if not input_str:
                    continue

                parts = input_str.split('/', 1)
                command_name = parts[0].upper()
                arguments_str = parts[1] if len(parts) > 1 else ""
                requires_session = self.COMMANDS.get(command_name)

                if requires_session is True:
                    if not self.session:
                        self._log(f"Error: Command '{command_name}' requires a session, but you are not logged in.")
                        continue
                    final_command_payload = f"{command_name}/{self.session}"
                    if arguments_str:
                        final_command_payload += f"/{arguments_str}"
                    self._log(f"(Session required) Preparing payload: {final_command_payload}")

                elif requires_session is False:
                    final_command_payload = input_str
                    self._log(f"(No session command) Preparing payload: {final_command_payload}")

                else:
                    self._log(
                        f"Warning: Command '{command_name}' is not in the known list. Assuming no session required.")
                    final_command_payload = input_str
                    self._log(f"(Unknown command) Preparing payload: {final_command_payload}")

                if not self.send(final_command_payload):
                    break

                response = self.receive()
                if response:
                    self._log(f"Response: {response}")
                elif not self.is_running:
                    self._log("Connection lost during receive.")
                    break

        except KeyboardInterrupt:
            self._log("Ctrl+C detected, closing connection.")
        finally:
            self.close()
            self._log("Command line closed.")
            
    def update_server_status(self):
        if self.session:
            payload = f"UPDATE_LOCATION/{self.session}/{self.lat:.6f}/{self.lon:.6f}/{self.state}"
            self.send(payload)
            
    def is_position_occupied(self, lat: float, lon: float) -> bool:
        session = get_db_session()
        try:
            count = session.query(Vehicle).filter(
                Vehicle.vehicle_id != self.id,
                abs(Vehicle.latitude - lat) < 0.0001,
                abs(Vehicle.longitude - lon) < 0.0001
            ).count()
            return count > 0
        finally:
            session.close()
            
    def load_route_from_db(self) -> None:
        """Load the route for this vehicle from the database."""
        session = get_db_session()
        route_steps = (
            session.query(Routes)
            .filter_by(vehicle_id=self.id)
            .order_by(Routes.step_index)
            .all()
        )
        self.route = [step.place_id for step in route_steps]
        self._log(f"Loaded route: {self.route}")

    def run_route_loop(self) -> None:
        """Continuously move along the route."""
        self._log("Starting run_route_loop()")
        while self.is_running:
            if self.state == "IDLE" and self.route:
                next_place_id = self.route[self.current_index]
                next_place = get_place_by_id(next_place_id)
                if not next_place:
                    self._log(f"Error: Place {next_place_id} not found.")
                    self.state = "IDLE"
                    continue

                # Preemptive check for place capacity
                if not next_place.pass_through and is_place_full(next_place_id):
                    self._log(f"{next_place_id} is full. Waiting before approaching.")
                    self.state = "DELAYED"
                    self.update_server_status()
                    time.sleep(1)
                    continue

                self._log(f"Moving to {next_place_id} ({next_place.latitude}, {next_place.longitude})")
                self.state = "MOVING"
                self.update_server_status()

            elif self.state == "MOVING":
                next_place_id = self.route[self.current_index]
                next_place = get_place_by_id(next_place_id)

                if not next_place:
                    self._log(f"Error: Place {next_place_id} not found.")
                    self.state = "IDLE"
                    continue

                # Calculate the next step toward the target
                new_lat = self.lat + (next_place.latitude - self.lat) * 0.1
                new_lon = self.lon + (next_place.longitude - self.lon) * 0.1

                # Check for positional congestion
                if self.is_position_occupied(new_lat, new_lon):
                    self._log(f"Blocked by vehicle ahead at ({new_lat:.6f}, {new_lon:.6f}). Waiting...")
                    self.state = "DELAYED"
                    self.update_server_status()
                    time.sleep(1)
                    continue

                # Update position
                self.lat = new_lat
                self.lon = new_lon
                self._log(f"Current location: ({self.lat:.6f}, {self.lon:.6f})")
                self.update_server_status()

                # Distance-based arrival detection
                def euclidean_dist(lat1, lon1, lat2, lon2):
                    return ((lat1 - lat2)**2 + (lon1 - lon2)**2) ** 0.5

                if euclidean_dist(self.lat, self.lon, next_place.latitude, next_place.longitude) < 0.00005:
                    self._log(f"Arrived at {next_place_id}")
                    success, status = try_enter_place(self.id, next_place_id)
                    if success:
                        self._log(f"Entered {next_place_id}: {status}")

                        if next_place.pass_through:
                            self._log(f"{next_place_id} is a pass-through. Skipping wait.")
                            remove_vehicle_from_place(self.id)
                            self.current_index += 1
                            if self.current_index >= len(self.route):
                                self.state = "FINISHED"
                                self._log("Route complete. Vehicle finished.")
                                self.update_server_status()
                                break
                            else:
                                self.state = "IDLE"
                                self.update_server_status()
                        else:
                            self.state = "WAITING"
                            self.update_server_status()
                            time.sleep(next_place.stay_time_seconds or 60)
                            remove_vehicle_from_place(self.id)
                            self._log(f"Leaving {next_place_id}")
                            self.current_index += 1
                            if self.current_index >= len(self.route):
                                self.state = "FINISHED"
                                self._log("Route complete. Vehicle finished.")
                                self.update_server_status()
                                break
                            else:
                                self.state = "IDLE"
                                self.update_server_status()
                    else:
                        self._log(f"Failed to enter {next_place_id}: {status}")
                        self.delayed = True
                        self.state = "DELAYED"
                        self.update_server_status()
                        time.sleep(5)
                        self.delayed = False
                        self.state = "MOVING"
                        self.update_server_status()

            time.sleep(1)
            
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python Vehicle.py <vehicle_id>")
        exit(1)

    vehicle_id = sys.argv[1]
    SERVER_ADDRESS = "localhost"
    SERVER_PORT = 8000
    
    prefix_map = {
        "B": VehicleType.BUS,
        "U": VehicleType.UBER,
        "S": VehicleType.SHUTTLE,
        "T": VehicleType.TRAIN,
    }

    vtype = prefix_map.get(vehicle_id[0].upper())
    if not vtype:
        print(f"Unknown vehicle type for ID: {vehicle_id}")
        exit(1)

    v = Vehicle(vehicle_id, vtype, (SERVER_ADDRESS, SERVER_PORT))
    v.run()

