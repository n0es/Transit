from typing import Tuple, Dict
from enum import Enum
import threading
import socket
import time
import random

class VehicleType(Enum):
    TRAIN = "T"
    BUS = "B"
    UBER = "U"
    SHUTTLE = "S"


class Vehicle:
    COMMANDS: Dict[str, bool] = {
        "REGISTER": False,
        "LOGIN": False,
    }
    def __init__(self, id: str, type: VehicleType, server_addr: Tuple[str, int], udp_port: int, password: str = None, session: str = None) -> None:
        self.is_running = False
        self.id = id
        self.password = password
        self.session = session
        self.type = type
        if self.id[0]!=type.value:
            raise ValueError(f"Vehicle ID must correlate with vehicle type!\nID = {self.id}\nType = {self.type.value}")

        self.server_tcp_addr = server_addr
        self.server_udp_addr = (server_addr[0], udp_port)

        self.tcp_client: socket.socket | None = None
        self.udp_client: socket.socket | None = None
        self.beacon_thread: threading.Thread | None = None
        self.beacon_interval: int = 10

        self.current_latitude: float = 40.7 + random.uniform(-0.05, 0.05)
        self.current_longitude: float = -74.0 + random.uniform(-0.05, 0.05)

        self.connect(server_addr)

    def _log(self, msg: str) -> None:
        print(self.id + " | " + msg)

    def connect(self, address):
        try:
            self.tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_client.connect(address)
            self._log("TCP Connection established!")
        except socket.error as e:
            self._log(f"TCP Connection failed: {e}")
            self.tcp_client = None
            return

        try:
            self.udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._log("UDP socket created.")
        except socket.error as e:
            self._log(f"UDP socket creation failed: {e}")
            self.udp_client = None

    def send(self, command_payload: str) -> bool:
        if not self.tcp_client:
            self._log("Cannot send TCP: Not connected.")
            return False
        msg = f"{self.id}/{command_payload}"
        try:
            self._log(f"Sending TCP: {msg}")
            self.tcp_client.sendall(msg.encode())
            return True
        except socket.error as e:
            self._log(f"Error sending TCP message: {e}")
            self._handle_disconnect()
            return False
        except Exception as e:
            self._log(f"Unexpected error sending TCP message: {e}")
            self._handle_disconnect()
            return False

    def send_udp_beacon(self) -> None:
        if not self.udp_client or not self.is_running:
            return
        self.current_latitude += random.uniform(-0.0001, 0.0001)
        self.current_longitude += random.uniform(-0.0001, 0.0001)

        message = f"{self.id}/{self.current_longitude:.6f}/{self.current_latitude:.6f}"
        try:
            self.udp_client.sendto(message.encode(), self.server_udp_addr)
        except socket.error as e:
            self._log(f"Error sending UDP beacon: {e}")
        except Exception as e:
            self._log(f"Unexpected error sending UDP beacon: {e}")

    def _beacon_loop(self) -> None:
        self._log(f"Starting UDP beacon loop (interval: {self.beacon_interval}s)")
        while self.is_running:
            self.send_udp_beacon()
            time.sleep(self.beacon_interval)
        self._log("UDP beacon loop stopped.")

    def receive(self) -> str:
        if not self.tcp_client:
            self._log("Cannot receive TCP: Not connected.")
            return ""
        try:
            data = self.tcp_client.recv(1024).decode()
            if not data:
                self._log("Receive TCP failed: Connection closed by server.")
                self._handle_disconnect()
                return ""
            self._log(f"Received TCP: {data}")
            return data
        except socket.timeout:
            self._log(f"Receive TCP timed out.")
            return ""
        except socket.error as e:
            self._log(f"Error receiving TCP message: {e}")
            self._handle_disconnect()
            return ""
        except Exception as e:
            self._log(f"Unexpected error receiving TCP message: {e}")
            self._handle_disconnect()
            return ""

    def _handle_disconnect(self):
        self._log("Handling TCP disconnection...")
        self.is_running = False
        if self.tcp_client:
            try:
                self.tcp_client.close()
            except socket.error:
                pass
            self.tcp_client = None
        self.session = None

    def close(self) -> None:
        self._log("Initiating manual close...")
        self.is_running = False

        if self.beacon_thread and self.beacon_thread.is_alive():
            self._log("Waiting for beacon thread...")
            self.beacon_thread.join(timeout=1.0)

        if self.tcp_client:
            try:
                self.tcp_client.close()
                self._log("TCP Connection closed")
            except socket.error as e:
                self._log(f"Error closing TCP connection: {e}")
            finally:
                 self.tcp_client = None

        if self.udp_client:
            try:
                self.udp_client.close()
                self._log("UDP socket closed")
            except socket.error as e:
                self._log(f"Error closing UDP socket: {e}")
            finally:
                self.udp_client = None

        self._log("Vehicle closed.")

    def run(self) -> None:
        if not self.tcp_client:
            self._log("Cannot run: Not connected.")
            return

        self.register()

        if not self.session:
            self._log("Startup failed: Could not establish session.")
            self.close()
            return

        self.is_running = True

        if self.udp_client:
            self.beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True)
            self.beacon_thread.start()
        else:
            self._log("UDP beacon thread not started (UDP client not available).")

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
        login_cmd = f"LOGIN"
        if self.password:
            login_cmd += f"/{self.password}"

        if not self.send(login_cmd): return

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
            while self.is_running and self.tcp_client:
                input_str = input(f"{self.id}> ").strip()
                if not input_str:
                    continue

                parts = input_str.split('/', 1)
                command_name = parts[0].upper()
                arguments_str = parts[1] if len(parts) > 1 else ""
                requires_session = self.COMMANDS.get(command_name)

                if command_name in ["REGISTER", "LOGIN"]:
                    final_command_payload = input_str
                    self._log(f"(Auth command) Preparing payload: {final_command_payload}")
                elif requires_session is True:
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
                    self._log(f"Warning: Command '{command_name}' is not in the known list. Assuming session required.")
                    if not self.session:
                        self._log(f"Error: Command '{command_name}' requires a session, but you are not logged in.")
                        continue
                    final_command_payload = f"{command_name}/{self.session}"
                    if arguments_str:
                        final_command_payload += f"/{arguments_str}"
                    self._log(f"(Unknown command - session assumed) Preparing payload: {final_command_payload}")

                if not self.send(final_command_payload):
                    break

                response = self.receive()
                if response:
                    pass
                elif not self.is_running:
                    self._log("Connection lost during receive.")
                    break

        except KeyboardInterrupt:
            self._log("Ctrl+C detected, closing connection.")
        except EOFError:
            self._log("Input stream closed, closing connection.")
        finally:
            self.close()
            self._log("Command line closed.")


if __name__ == '__main__':
    SERVER_ADDRESS = "localhost"
    TCP_SERVER_PORT = 8000
    UDP_SERVER_PORT = 8001

    v = Vehicle("B101", VehicleType.BUS, (SERVER_ADDRESS, TCP_SERVER_PORT), UDP_SERVER_PORT)
    v.run()