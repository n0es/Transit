from abc import ABC, abstractmethod
from Vehicle import VehicleType
import threading
import sqlite3
import socket
import uuid
import datetime
import time
from sqlalchemy.orm import Session
from Database import Vehicle, Session as DBSession, Location, get_db_session

class Database:
    def __init__(self):
        self.session = get_db_session()

    def vehicle_exists(self, vehicle_id: str) -> bool:
        return self.session.query(Vehicle).filter_by(vehicle_id=vehicle_id).first() is not None

    def create_session(self, vehicle_id: str) -> str:
        session_id = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=1)
        new_session = DBSession(session_id=session_id, vehicle_id=vehicle_id, expires_at=expires_at)
        self.session.add(new_session)
        self.session.commit()
        return session_id

    def validate_session(self, session_id: str, expected_vehicle_id: str) -> tuple[bool, str]:
        db_session = self.session.query(DBSession).filter_by(session_id=session_id).first()
        if not db_session:
            return False, "INVALID_SESSION"

        if db_session.vehicle_id != expected_vehicle_id:
            return False, "INVALID_SESSION"

        if datetime.datetime.now() > db_session.expires_at:
            return False, "SESSION_EXPIRED"

        return True, "VALID"

    def record_location(self, vehicle_id: str, longitude: float, latitude: float) -> bool:
        try:
            new_location = Location(vehicle_id=vehicle_id, longitude=longitude, latitude=latitude)
            self.session.add(new_location)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Error recording location: {e}")
            return False

    def register_vehicle(self, vehicle_id: str, vehicle_type: str) -> bool:
        try:
            new_vehicle = Vehicle(vehicle_id=vehicle_id, vehicle_type=vehicle_type)
            self.session.add(new_vehicle)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Error registering vehicle: {e}")
            return False


class TransitSystem:
    def __init__(self, tcp_port: int, udp_port: int):
        self.db = Database()
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tcp_socket.bind(('0.0.0.0', tcp_port))
        self.udp_socket.bind(('0.0.0.0', udp_port))
        self.tcp_socket.settimeout(1.0)
        self.tcp_socket.listen(5)
        self._log(f'TCP Server listening on 0.0.0.0:{tcp_port}')
        self._log(f'UDP Server listening on 0.0.0.0:{udp_port}')

        self.running = False
        self.udp_thread = None

    def _log(self, *args):
        msg = " ".join(map(str, args))
        print('Server | ' + msg)

    def start(self):
        self.running = True
        self.udp_thread = threading.Thread(target=self._handle_udp_location, daemon=True)
        self.udp_thread.start()
        self._log("UDP listener thread started.")

        try:
            while self.running:
                try:
                    conn, addr = self.tcp_socket.accept()
                    threading.Thread(
                        target=self.handle_client, args=(conn, addr), daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self._log(f'Error connecting: {e}')
                    break
        except KeyboardInterrupt:
            self._log('Server stopping...')
        finally:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self._log('Closing server...')
        try:
            self.tcp_socket.shutdown(socket.SHUT_RDWR)
        except (socket.error, OSError) as e:
            self._log(f"Error during TCP socket shutdown (ignoring): {e}")
        try:
            self.tcp_socket.close()
            self._log('TCP socket closed.')
        except Exception as e:
            self._log(f"Error closing TCP socket: {e}")

        try:
            self.udp_socket.close()
            self._log('UDP socket closed.')
        except Exception as e:
            self._log(f"Error closing UDP socket: {e}")

        if self.udp_thread and self.udp_thread.is_alive():
             self._log("Waiting for UDP thread to finish...")
             self.udp_thread.join(timeout=2.0)
             if self.udp_thread.is_alive():
                 self._log("UDP thread did not finish cleanly.")

        self._log('Server stopped.')

    def _handle_udp_location(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                msg = data.decode().strip()
                self._log(f"[UDP {addr}] Received: {msg}")

                parts = msg.split('/')
                if len(parts) == 3:
                    vehicle_id, lon_str, lat_str = parts
                    try:
                        longitude = float(lon_str)
                        latitude = float(lat_str)
                        if self.db.record_location(vehicle_id, longitude, latitude):
                            self._log(f"[UDP {addr}] Recorded location for {vehicle_id}: ({longitude}, {latitude})")
                        else:
                            self._log(f"[UDP {addr}] Failed to record location for {vehicle_id}")
                    except ValueError:
                        self._log(f"[UDP {addr}] Invalid location format in message: {msg}")
                    except Exception as e:
                         self._log(f"[UDP {addr}] Error processing location for {vehicle_id}: {e}")
                else:
                    self._log(f"[UDP {addr}] Invalid UDP message format: {msg}")

            except socket.error as e:
                if self.running:
                    self._log(f"[UDP Listener] Socket Error: {e}")
                else:
                    self._log("[UDP Listener] Socket closed, shutting down.")
                    break
            except Exception as e:
                self._log(f"[UDP Listener] Unexpected error: {e}")
                time.sleep(1)

    def handle_client(self, conn, addr):
        self._log(f'[{addr}] Client connected')
        try:
            while True:
                data = conn.recv(1024)
                if data:
                    msg = data.decode().strip()
                    self._log(f'[{addr}] {msg}')
                    if not msg:
                        continue
                    self.handle_command(addr, conn, msg)
        except socket.error as e:
            self._log(f'[{addr}] Socket Error: {e}')
        except Exception as e:
            self._log(f'[{addr}] Unexpected error: {e}')
        finally:
            conn.close()
            self._log(f'[{addr}] Client connection closed')

    def handle_command(self, addr, sock_conn, args):
        args = args.split('/')
        if len(args) < 2:
            self._log(f"[{addr}] Received invalid command: {args}")
            sock_conn.sendall("ERROR/Invalid format, use `ID/COMMAND/*ARGS`".encode())
            return

        vid = args[0]
        cmd_name = args[1].upper()
        args = args[2:]

        command = Command.COMMANDS.get(cmd_name)
        if not command:
            self._log(f"[{addr}] Received invalid command: {cmd_name}")
            sock_conn.sendall(f"ERROR/Invalid command: {cmd_name}".encode())
            return

        try:
            cmd_instance = command(vid, sock_conn, self.db, args)
            self._log(f"[{addr}] Executed command: {cmd_name}")
            cmd_instance.execute()
        except Exception as e:
            self._log(f"[{addr}] Unexpected error while processing command: {e}")

class Command(ABC):
    COMMANDS: dict[str, type['Command']] = {}
    COMMAND_NAME: str | None = None
    ARGS_EXPECTED: int | None = None
    ARGS_MIN: int | None = None

    def __init__(self, vid: str, sock_conn, db: Database, args: list[str]) -> None:
        self.vid = vid
        self.sock_conn = sock_conn
        self.db = db
        self.args = args

    def _log(self, *args):
        msg = " ".join(map(str, args))
        print(f'[{self.vid}/{self.__class__.__name__}] | {msg}')

    def send_response(self, *args: str):
        message = "/".join(args)
        try:
            self.sock_conn.sendall(message.encode())
            self._log(f'Responded with: {message}')
        except socket.error as e:
            self._log(f"Error sending response: {e}")

    def _validate_args(self) -> bool:
        if self.ARGS_EXPECTED is not None:
            if len(self.args) != self.ARGS_EXPECTED:
                self._log(f'ERROR: Expected {self.ARGS_EXPECTED} arguments, got {len(self.args)}')
                return False
            return True

        if self.ARGS_MIN is not None:
            if len(self.args) < self.ARGS_MIN:
                self._log(f'ERROR: Expected at least {self.ARGS_MIN} arguments, got {len(self.args)}')
                return False
            return True

        return True

    def execute(self):
        self._log(f"Command sent with args: {self.args}")

        if not self._validate_args():
            return

        try:
            self._execute()
        except Exception as e:
            self._log(f"Unexpected error during execution: {e}")
            self.send_response(f"ERROR:Internal server error")

    @abstractmethod
    def _execute(self):
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if cls.COMMAND_NAME is None:
            print(f"Skipping command registration for {cls.__name__} (no COMMAND_NAME)")
            return

        name = cls.COMMAND_NAME.upper()
        print(f"Registering command: {name} -> {cls.__name__}")
        Command.COMMANDS[name] = cls


class SessionCommand(Command):
    ARGS_MIN = 1

    def __init__(self, vid: str, sock_conn, db: Database, args: list[str]) -> None:
        super().__init__(vid, sock_conn, db, args)
        self.session_id: str | None = None

    def _validate_args(self) -> bool:
        if not super()._validate_args():
            self._log("Base argument validation failed.")
            return False

        extracted_session_id = self.args[0]

        self._log(f"Validating session ID: {extracted_session_id} for vehicle {self.vid}")
        is_valid, validation_message = self.db.validate_session(extracted_session_id, self.vid)

        if not is_valid:
            self._log(f"Session validation failed: {validation_message}")
            self.send_response(f"ERROR/{validation_message}")
            return False

        self.session_id = extracted_session_id
        self._log("Session validation successful.")

        self.args = self.args[1:]

        expected = self.__class__.ARGS_EXPECTED
        min = self.__class__.ARGS_MIN
        if expected is not None:
            if len(self.args) != expected:
                err_msg = f"ERROR: {self.COMMAND_NAME} requires {expected} arguments after session ID, got {len(self.args)}."
                self._log(err_msg)
                self.send_response(err_msg)
                return False
            self._log(f"Validated specific arg count ({expected}) for subclass.")

        if min is not None:
            if len(self.args) < min:
                err_msg = f"ERROR: {self.COMMAND_NAME} requires at least {min} arguments after session ID, got {len(self.args)}."
                self._log(err_msg)
                self.send_response(err_msg)
                return False
            self._log(f"Validated minimum arg count ({min}) for subclass.")

        return True

class RegisterCommand(Command):
    COMMAND_NAME = "REGISTER"

    def _execute(self):
        vehicle_type = VehicleType(self.vid[0])

        self._log(f'Checking DB for vehicle {self.vid}')
        if self.db.vehicle_exists(self.vid):
            self._log(f'Vehicle {self.vid} already registered.')
            self.send_response("EXISTS")
            return

        self._log(f'Registering vehicle {self.vid}...')
        if self.db.register_vehicle(self.vid, vehicle_type.value):
            self._log(f'Vehicle registration successful: {self.vid}')
            session = self.db.create_session(self.vid)
            self.send_response(self.vid, session)
        else:
            self._log(f'Vehicle registration failed for: {self.vid}')
            self.send_response("ERROR/Registration failed")

class LoginCommand(Command):
    COMMAND_NAME = "LOGIN"

    def _execute(self):

        self._log(f'Checking DB for vehicle {self.vid}')
        if not self.db.vehicle_exists(self.vid):
            self._log(f'Vehicle {self.vid} is not registered.')
            self.send_response("UNREGISTERED/Please register your vehicle")
            return

        self._log(f'Login successful')
        session = self.db.create_session(self.vid)
        self.send_response(self.vid, session)

if __name__ == '__main__':
    TCP_SERVER_PORT = 8000
    UDP_SERVER_PORT = 8001
    s = TransitSystem(TCP_SERVER_PORT, UDP_SERVER_PORT)
    s.start()