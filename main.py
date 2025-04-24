from abc import ABC, abstractmethod
from Vehicle import VehicleType
import threading
import sqlite3
import socket
import uuid
import datetime
from sqlalchemy.orm import Session
from Database import Vehicle, Session as DBSession, Location, get_db_session

class Database:
    def __init__(self):
        self.session = get_db_session()

    def vehicle_exists(self, vehicle_id: str) -> bool:
        return self.session.query(Vehicle).filter_by(vehicle_id=vehicle_id).first() is not None

    def vehicle_password_correct(self, vehicle_id: str, password: str) -> bool:
        vehicle = self.session.query(Vehicle).filter_by(vehicle_id=vehicle_id, vehicle_password=password).first()
        return vehicle is not None

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

    def register_vehicle(self, vehicle_id: str, vehicle_password: str, vehicle_type: str) -> bool:
        try:
            new_vehicle = Vehicle(vehicle_id=vehicle_id, vehicle_password=vehicle_password, vehicle_type=vehicle_type)
            self.session.add(new_vehicle)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Error registering vehicle: {e}")
            return False


class TransitSystem:
    def __init__(self, port: int):
        self.db = Database()  # Use the SQLAlchemy-based Database class
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(('0.0.0.0', port))
        self.socket.listen(5)
        self._log(f'Server listening on 0.0.0.0:{port}')

        self.running = False

    def _log(self, *args):
        msg = " ".join(map(str, args))
        print('Server | ' + msg)

    def start(self):
        self.running = True
        try:
            while self.running:
                try:
                    conn, addr = self.socket.accept()
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
        self.running = False
        self._log('Closing server...')
        self.socket.close()
        self._log('Server stopped.')

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
            cmd_instance = command(vid, sock_conn, self.db, args)  # Pass the Database instance
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
        self.db = db  # Use the SQLAlchemy-based Database instance
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
        
        if cls is Command:
            return

        if not cls.COMMAND_NAME:
            print('Command registration failed: no COMMAND_NAME')
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
        password = self.args[0] if len(self.args) > 0 else None

        self._log(f'Checking DB for vehicle {self.vid}')
        if self.db.vehicle_exists(self.vid):
            self._log(f'Vehicle {self.vid} already registered.')
            self.send_response("EXISTS")
            return

        self._log(f'Registering vehicle {self.vid}...')
        if self.db.register_vehicle(self.vid, password, vehicle_type.value):
            self._log(f'Vehicle registration successful: {self.vid}')
            session = self.db.create_session(self.vid)
            self.send_response(self.vid, session)
        else:
            self._log(f'Vehicle registration failed for: {self.vid}')
            self.send_response("ERROR/Registration failed")

class LoginCommand(Command):
    COMMAND_NAME = "LOGIN"

    def _execute(self):
        password = self.args[0] if len(self.args) > 0 else None

        self._log(f'Checking DB for vehicle {self.vid}')
        if not self.db.vehicle_exists(self.vid):
            self._log(f'Vehicle {self.vid} is not registered.')
            self.send_response("UNREGISTERED/Please register your vehicle")
            return

        if not self.db.vehicle_password_correct(self.vid, password):
            self._log(f'Invalid password')
            self.send_response("INVALID/Invalid vehicle id or password")
            return

        self._log(f'Login successful')
        session = self.db.create_session(self.vid)
        self.send_response(self.vid, session)

class UpdateLocationCommand(SessionCommand):
    COMMAND_NAME = "UPDATE_LOCATION"
    EXPECTED_ARGS_COUNT = 2

    def _execute(self):
        if len(self.args) != 2:
            self._log("Internal error: Incorrect number of args in _execute_logic.")
            self.send_response("ERROR/Internal argument processing error")
            return

        try:
            longitude = float(self.args[0])
            latitude = float(self.args[1])
        except ValueError:
            self._log(f"Invalid location format: {self.args}")
            self.send_response("ERROR/Invalid location format. Longitude/Latitude must be numbers.")
            return

        self._log(f"Attempting to record location ({longitude}, {latitude})")

        if self.db.record_location(self.vid, longitude, latitude):
            self.send_response("OK/Location Updated")
        else:
            self.send_response("ERROR/Failed to update location in database")

if __name__ == '__main__':
    SERVER_PORT = 8000
    s = TransitSystem(SERVER_PORT)
    s.start()