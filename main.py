from abc import ABC, abstractmethod
from Vehicle import VehicleType
import threading
import sqlite3
import socket
import uuid
import datetime

class Database:
    def __init__(self, path):
        self.path = path
        self._init_tables()

    def _init_tables(self):
        self._log("Ensuring tables exist")
        conn = None
        try:
            conn = sqlite3.connect(self.path)
            self._log("Connected to SQLite")
            cur = conn.cursor()

            self._init_vehicles(conn, cur)
            self._init_sessions(conn, cur)
            self._init_locations(conn, cur)

        except sqlite3.Error as e:
            self._log(f"Error during database initialization: {e}")
        finally:
            if conn:
                conn.close()
                self._log('SQLite connection closed')

    def _init_vehicles(self, conn, cursor):
        self._log('Initializing table: vehicles')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
        vehicle_id TEXT PRIMARY KEY,
        vehicle_password TEXT,
        vehicle_type TEXT NOT NULL,
        status TEXT NOT NULL
        )''')
        conn.commit()
        self._log('Vehicles initialized!')

    def _init_sessions(self, conn, cursor):
        self._log('Initializing table: sessions')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        vehicle_id TEXT NOT NULL,
        expires_at INTEGER NOT NULL
        )''')
        conn.commit()
        self._log('Sessions initialized!')

    def _init_locations(self, conn, cursor):
        self._log('Initializing table: locations')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
        location_id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehicle_id TEXT NOT NULL,
        longitude REAL NOT NULL,
        latitude REAL NOT NULL,
        timestamp TEXT NOT NULL DEFAULT current_timestamp
        )''')
        conn.commit()
        self._log('Locations initialized!')

    @staticmethod
    def _log(message):
        print("DB | "+message)

    @staticmethod
    def vehicle_exists(cursor, vehicle_id: str) -> bool:
        cursor.execute('SELECT EXISTS(SELECT 1 FROM vehicles WHERE vehicle_id = ?)', (vehicle_id,))
        result = cursor.fetchone()
        return result is not None and result[0] > 0

    @staticmethod
    def vehicle_password_correct(cursor, vehicle_id: str, password: str) -> bool:
        cursor.execute('SELECT EXISTS(SELECT 1 FROM vehicles WHERE vehicle_id = ? AND vehicle_password = ?)', (vehicle_id, password))
        return cursor.fetchone() is not None

    @staticmethod
    def create_session(conn, cursor, vehicle_id: str) -> str:
        session_id = str(uuid.uuid4())
        expires_at_dt = datetime.datetime.now() + datetime.timedelta(hours=1)
        expires_at_ts = int(expires_at_dt.timestamp())
        try:
            cursor.execute('''
            INSERT INTO sessions (session_id, vehicle_id, expires_at)
            VALUES (?, ?, ?)
            ''', (session_id, vehicle_id, expires_at_ts))
            conn.commit()
            Database._log(f"Created session {session_id} for {vehicle_id} expiring at {expires_at_dt}")
            Database._log(session_id)
            return session_id
        except sqlite3.Error as e:
            Database._log(f"Error creating session for {vehicle_id}: {e}")
            conn.rollback()
            return ""

    @staticmethod
    def validate_session(cursor, session_id: str, expected_vehicle_id: str) -> tuple[bool, str]:
        if not session_id:
            return False, "SESSION_ID_MISSING"

        try:
            cursor.execute("SELECT vehicle_id, expires_at FROM sessions WHERE session_id = ?", (session_id,))
            result = cursor.fetchone()

            if not result:
                Database._log(f"Session validation failed: Session ID '{session_id}' not found.")
                return False, "INVALID_SESSION"

            actual_vehicle_id, expires_at_ts = result

            if actual_vehicle_id != expected_vehicle_id:
                Database._log(
                    f"Session validation failed: Mismatch for session '{session_id}'. Expected '{expected_vehicle_id}', found '{actual_vehicle_id}'.")
                return False, "INVALID_SESSION"

            current_time_ts = int(datetime.datetime.now().timestamp())
            if current_time_ts > expires_at_ts:
                Database._log(
                    f"Session validation failed: Session '{session_id}' for vehicle '{expected_vehicle_id}' expired at {datetime.datetime.fromtimestamp(expires_at_ts)}.")
                return False, "SESSION_EXPIRED"

            Database._log(f"Session validation successful for session '{session_id}', vehicle '{expected_vehicle_id}'.")
            return True, "VALID"

        except sqlite3.Error as e:
            Database._log(f"Database error during session validation for '{session_id}': {e}")
            return False, "DB_ERROR"
        except Exception as e:
            Database._log(f"Unexpected error during session validation for '{session_id}': {e}")
            return False, "UNEXPECTED_ERROR"

    @staticmethod
    def record_location(conn, cursor, vehicle_id: str, longitude: float, latitude: float) -> bool:
        try:
            cursor.execute('''
                   INSERT INTO locations (vehicle_id, longitude, latitude)
                   VALUES (?, ?, ?)
               ''', (vehicle_id, longitude, latitude))
            conn.commit()
            Database._log(f"Recorded location for {vehicle_id}: ({longitude}, {latitude})")
            return True
        except sqlite3.Error as e:
            Database._log(f"Error recording location for {vehicle_id}: {e}")
            conn.rollback()
            return False

    @staticmethod
    def register_vehicle(conn, cursor, vehicle_id: str, vehicle_password: str, vehicle_type: VehicleType):
        status = "IDLE"
        try:
            cursor.execute('''
                INSERT INTO vehicles (vehicle_id, vehicle_password, vehicle_type, status)
                VALUES (?, ?, ?, ?)
            ''', (vehicle_id, vehicle_password, vehicle_type.value, status))
            conn.commit()
            Database._log(f"Registered vehicle {vehicle_id}")
            return True
        except sqlite3.IntegrityError:
            Database._log(f"Vehicle {vehicle_id} already exists (IntegrityError).")
            return False
        except sqlite3.Error as e:
            Database._log(f"Error registering vehicle {vehicle_id}: {e}")
            conn.rollback()
            return False


class TransitSystem:
    def __init__(self, db_path: str, port: int):
        self.db_path = db_path
        Database(self.db_path)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(('0.0.0.0', port))
        self.socket.listen(5)
        self._log(f'Server listening on 0.0.0.0:{port}')

        self.running = False

    def _log(self, *args):
        msg = " ".join(map(str, args))
        print('Server | '+msg)

    def start(self):
        self.running = True
        try:
            while self.running:
                try:
                    conn, addr = self.socket.accept()
                    client_thread = threading.Thread(
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
        db_conn = None
        try:
            db_conn = sqlite3.connect(self.db_path)
            self._log(f'[{addr}] SQLite connection established for thread')

            while True:
                data = conn.recv(1024)
                if data:
                    msg = data.decode().strip()
                    self._log(f'[{addr}] {msg}')
                    if not msg:
                        continue
                    self.handle_command(addr, conn, db_conn, msg)
        except socket.error as e:
            self._log(f'[{addr}] Socket Error: {e}')
        except sqlite3.Error as e:
            self._log(f'[{addr}] Database Error: {e}')
        except Exception as e:
            self._log(f'[{addr}] Unexpected error: {e}')
        finally:
            if db_conn:
                db_conn.close()
                self._log(f'[{addr}] SQLite connection closed for thread')
            conn.close()
            self._log(f'[{addr}] Client connection closed')

    def handle_command(self, addr, sock_conn, db_conn, args):
        args = args.split('/')
        if len(args) < 2:
            self._log(f"[{addr}] Received invalid command: {args}")
            sock_conn.sendall("ERROR/Invalid format, use `ID/COMMAND/*ARGS`")
            return

        vid = args[0]
        cmd_name = args[1].upper()
        args = args[2:]

        command = Command.COMMANDS.get(cmd_name)
        if not command:
            self._log(f"[{addr}] Received invalid command: {cmd_name}")
            sock_conn.sendall(f"ERROR/Invalid command: {cmd_name}")

        try:
            cmd_instance = command(vid, sock_conn, db_conn, args)

            self._log(f"[{addr}] Executed command: {cmd_name}")
            cmd_instance.execute()
        except Exception as e:
            self._log(f"[{addr}] Unexpected error while processing command: {e}")

class Command(ABC):
    COMMANDS: dict[str, type['Command']] = {}  #
    COMMAND_NAME: str | None = None
    ARGS_EXPECTED: int | None = None
    ARGS_MIN: int | None = None
    def __init__(self, vid: str, sock_conn, db_conn, args: list[str]) -> None:
        self.vid = vid
        self.sock_conn = sock_conn
        self.db_conn = db_conn
        self.args = args

        self.cur = self.db_conn.cursor()

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
                self._log(f'ERROR: Expected at least {self.ARGS_EXPECTED} arguments, got {len(self.args)}')
                return False
            return True

        return True

    def execute(self):
        self._log(f"Command sent with args: {self.args}")

        if not self._validate_args():
            return

        try:
            self._execute()
        except sqlite3.Error as db_err:
            self._log(f"Database error during execution: {db_err}")
            self.send_response(f"ERROR:Database error")
        except Exception as e:
            self._log(f"Unexpected error during execution: {e}")
            self.send_response(f"ERROR:Internal server error")

    @abstractmethod
    def _execute(self):
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if not cls.COMMAND_NAME:
            print('Command registration failed: no COMMAND_NAME')
            return

        name = cls.COMMAND_NAME.upper()
        print(f"Registering command: {name} -> {cls.__name__}")
        Command.COMMANDS[name] = cls

class SessionCommand(Command):
    ARGS_MIN = 1

    def __init__(self, vid: str, sock_conn, db_conn, args: list[str]) -> None:
        super().__init__(vid, sock_conn, db_conn, args)
        self.session_id: str | None = None

    def _validate_args(self) -> bool:
        if not super()._validate_args():
            self._log("Base argument validation failed.")
            return False

        extracted_session_id = self.args[0]

        self._log(f"Validating session ID: {extracted_session_id} for vehicle {self.vid}")
        is_valid, validation_message = Database.validate_session(self.cur, extracted_session_id, self.vid)

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

    @abstractmethod
    def _execute(self):
        pass

    def execute(self):
         super().execute()

class RegisterCommand(Command):
    COMMAND_NAME = "REGISTER"

    def _execute(self):
        vehicle_type = VehicleType(self.vid[0])
        password = self.args[0] if len(self.args)>0 else None

        self._log(f'Checking DB for vehicle {self.vid}')
        if Database.vehicle_exists(self.cur, self.vid):
            self._log(f'Vehicle {self.vid} already registered.')
            self.send_response("EXISTS")
            return

        self._log(f'Registering vehicle {self.vid}...')
        if Database.register_vehicle(self.db_conn, self.cur, self.vid, password, vehicle_type):
            self._log(f'Vehicle registration successful: {self.vid}')
            session = Database.create_session(self.db_conn, self.cur, self.vid)
            self.send_response(self.vid, session)
        else:
             self._log(f'Vehicle registration failed for: {self.vid}')
             self.send_response("ERROR/Registration failed")

class LoginCommand(Command):
    COMMAND_NAME = "LOGIN"

    def _execute(self):
        password = self.args[0] if len(self.args)>0 else None

        self._log(f'Checking DB for vehicle {self.vid}')
        if not Database.vehicle_exists(self.cur, self.vid):
            self._log(f'Vehicle {self.vid} is not registered.')
            self.send_response("UNREGISTERED/Please register your vehicle")
            return

        if not Database.vehicle_password_correct(self.cur, self.vid, password):
            self._log(f'Invalid password')
            self.send_response("INVALID/Invalid vehicle id or password")
            return

        self._log(f'Login successful')
        session = Database.create_session(self.db_conn, self.cur, self.vid)
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

        if Database.record_location(self.db_conn, self.cur, self.vid, longitude, latitude):
            self.send_response("OK/Location Updated")
        else:
            self.send_response("ERROR/Failed to update location in database")


if __name__ == '__main__':
    DATABASE_NAME = 'transit.db'
    SERVER_PORT = 8000
    s = TransitSystem(DATABASE_NAME, SERVER_PORT)
    s.start()