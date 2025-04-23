from typing import Tuple, Dict
from enum import Enum
import threading
import socket

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


if __name__ == '__main__':
    SERVER_ADDRESS = "localhost"
    SERVER_PORT = 8000
    v = Vehicle("B101", VehicleType.BUS, (SERVER_ADDRESS, SERVER_PORT))
    v.run()