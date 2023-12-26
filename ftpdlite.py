"""
File systems in flight... FTPdLite!
(With apologies to Starland Vocal Band)

FTPdLite is a minimalist, mostly RFC-959 compliant, MicroPython FTP
server for 99% of your microcontroller file transferring needs.

(c)2023 David Horton.
Released under the BSD-2-Clause license.
Project site: https://github.com/DavesCodeMusings/ftpdlite

"""

# Many thanks to:
# D.J. Bernstein https://cr.yp.to/ftp.html for a clear explanation of FTP.
# Peter Hinch (peterhinch) for the proper `await start_server()` pattern.
# Robert Hammelrath (robert-hh) for assistance with FileZilla compatibility.
# ftp.freebsd.org for being there whenever I wondered how a server should behave.


from asyncio import get_event_loop, open_connection, sleep_ms, start_server
from time import localtime, time
from os import listdir, mkdir, remove, rename, rmdir, stat, statvfs, sync
from machine import deepsleep, reset
from gc import collect as gc_collect, mem_alloc, mem_free
from random import choice, seed
from cryptolib import aes
from hashlib import sha256
from binascii import b2a_base64


class Session:
    """
    An interactive connection from a client.
    """

    def __init__(self, client_ip, client_port, ctrl_reader, ctrl_writer):
        self.client_ip = client_ip
        self.client_port = client_port
        self.ctrl_reader = ctrl_reader
        self.ctrl_writer = ctrl_writer
        self.username = "nobody"
        self.uid = 65534
        self.cwd = "/"
        self.login_time = time()
        self.last_active_time = time()

    def has_write_access(self, path):
        """
        Given a file or directory path, report if writing by the user is allowed.

        Args:
            path: the absolute file or directory path to verify

        Returns:
            boolean: True if writable by the user, false if not
        """
        if self.uid == 0:
            return True
        else:
            return False


class SHA256AES:
    """
    Password hashing for FTPdLite User Accounts.
    """

    _method_token = "5a"  # Totally made up. Not a standard.

    @staticmethod
    def generate_salt(length):
        """
        Generate a random-character salt suitable for password hashing.
        """
        valid_chars = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        seed()
        salt = ""
        for i in range(length):
            salt += choice(valid_chars)
        return salt

    @staticmethod
    def create_salted_hash(salt, cleartext):
        """
        Given a salt value and password in cleartext, return a hashed password.
        """
        assert len(salt) % 16 == 0
        cleartext = bytes(cleartext, "utf8")
        cleartext += bytearray(16 - (len(cleartext) % 16))  # Pad out to 16-byte boundry
        cipher = aes(salt, 1)  # 1 is MODE_ECB, the only one supported by MicroPython
        salted_pw = cipher.encrypt(cleartext)
        return b2a_base64(sha256(salted_pw).digest()).decode("utf8").rstrip("\n")

    @staticmethod
    def create_passwd_entry(cleartext):
        salt = SHA256AES.generate_salt(16)  # Must be evenly divisible by 16 for AES
        hashed_pw = SHA256AES.create_salted_hash(salt, cleartext)
        return f"${SHA256AES._method_token}${salt}${hashed_pw}"

    @staticmethod
    def verify_passwd_entry(hashed, cleartext):
        """
        Given a hashed password, verify the cleartext password is valid.
        """
        if hashed.count("$") != 3:
            print("ERROR: Invalid hashed password format in credential entry.")
            return False
        else:
            _, hash_alg, salt, hashed_pw = hashed.split("$")
            if hash_alg != SHA256AES._method_token:
                print("ERROR: Unsupported hash algorithm in credential entry.")
            else:
                rehashed_pw = SHA256AES.create_salted_hash(salt, cleartext)
                if hashed_pw != rehashed_pw:
                    return False
                else:
                    return True


class FTPdLite:
    """
    Minimum functional FTP server with a severely limited command set.
    RFC-959, Section 5.1: Minimum Implementation + PASV support.
    """

    ENOENT = "No such file or directory."
    EACCES = "No access."
    _accounts = []
    _session_list = []

    def __init__(
        self,
        host="127.0.0.1",
        port=21,
        server_name="FTPdLite (MicroPython)",
        pasv_port_range=range(49152, 49407),
    ):
        self._debug = True
        self._host = host
        self._port = port
        self.max_connections = 10
        self.request_buffer_size = 512
        self._server_name = server_name
        self._pasv_port_pool = list(pasv_port_range)
        self._start_time = time()
        self._ftp_cmd_dict = {
            "MODE": self.mode,
            "NOOP": self.noop,
            "PASS": self.passwd,
            "PASV": self.pasv,
            "PORT": self.port,
            "QUIT": self.quit,
            "RETR": self.retr,
            "STOR": self.stor,
            "STRU": self.stru,
            "TYPE": self.type,
            "USER": self.user,
        }

    @staticmethod
    def decode_path(session, path):
        """
        Given a file or directory path, expand it to an absolute path.

        Args:
            path (string): a relative, absolute, or empty path to a resource
            session (object): the FTP client's session with cwd and home dir

        Returns:
            string: absolute path to resource
        """
        if path is None or path.startswith("-"):
            absolute_path = session.cwd  # client sent a command-line option, do nothing
        else:
            if path.startswith("/") is True:
                absolute_path = ""
            else:
                absolute_path = session.cwd
            path_components = path.split("/")
            for i in range(len(path_components)):
                if path_components[i] == "." or path_components[i] == "":
                    pass
                elif path_components[i] == "..":
                    absolute_path = absolute_path.rsplit("/", 1)[0] or ""
                else:
                    absolute_path = FTPdLite.path_join(
                        absolute_path, path_components[i]
                    )
        return absolute_path or "/"

    @staticmethod
    def path_join(*args):
        """
        There's no os.path.join available in MicroPython, so...

        Args:
            *args (string): a variable number of path components

        Returns:
            string: resulting absolute path
        """
        path_result = ""
        for path_component in args:
            if path_result.endswith("/") and path_component.startswith("/"):
                path_result += path_component.lstrip("/")
            elif path_result.endswith("/") or path_component.startswith("/"):
                path_result += path_component
            else:
                path_result += "/" + path_component
        return path_result

    @staticmethod
    def read_file_chunk(file):
        """
        Given a file handle, read the file in small chunks to avoid large buffer requirements.

        Args:
            file (object): the file handle returned by open()

        Returns:
            bytes: a chunk of the file until the file ends, then nothing
        """
        while True:
            chunk = file.read(512)  # small chunks to avoid out of memory errors
            if chunk:
                yield chunk
            else:  # empty chunk means end of the file
                return

    def debug(self, msg):
        if self._debug:
            print("DEBUG:", msg)

    async def delete_session(self, session):
        """
        Given a session object, delete it from the server's session list.

        Args:
            session (object): the client session of interest
        """
        for i in range(len(self._session_list)):
            if self._session_list[i] == session:
                await self.close_data_connection(session)
                await self.close_ctrl_connection(session)
                self.debug(
                    f"delete_session({session}) deleting: {session.username}@{session.client_ip}"
                )
                del self._session_list[i]
                break

    async def find_session(self, search_value):
        """
        Given a username or client IP address, find the associated sessions.

        Args:
            search_value (string): the username or IP of interest

        Returns:
            list[Session]: a list of matching Session objects
        """
        sessions_found = []
        if search_value and search_value[0].isdigit():
            for s in self._session_list:
                if s.client_ip == search_value:
                    sessions_found.append(s)
        else:
            for s in self._session_list:
                if s.username == search_value:
                    sessions_found.append(s)
        self.debug(f"find_session({search_value}) found: {sessions_found}")
        return sessions_found

    def parse_request(self, req_buffer):
        """
        Given a line of input, split the command into a verb and parameter.

        Args:
            req_buffer (bytes): the unprocessed request from the client

        Returns:
            verb (string): the requested FTP command
            param (string): the parameter, if any
        """
        try:
            request = req_buffer.decode("utf-8").rstrip("\r\n")
        except (OSError, UnicodeError):
            request = None
        if request is None or len(request) == 0:
            self.debug("Received NULL command. Interpreting as QUIT.")
            verb = "QUIT"  # Filezilla doesn't send QUIT, just NULL.
            param = None
        elif " " not in request:
            verb = request.upper()
            param = None
            self.debug(verb)
        else:
            verb = request.split(None, 1)[0].upper()
            try:
                param = request.split(None, 1)[1]
            except IndexError:
                param = ""
            if verb == "PASS":
                self.debug("PASS ********")
            else:
                self.debug(f"{verb} {param}")
        return verb, param

    async def send_response(self, session, code, msg=""):
        """
        Given a status code and a message, send a response to the client.

        Args:
            session (object): the FTP client's login session info
            code (integer): a three digit status code
            msg (string or list): a single-line (string) or multi-line (list)
                human readable message describing the result

        Returns:
            boolean: True if stream writer was up, false if not
        """
        success = True
        if isinstance(msg, str):  # single line
            self.debug(f"{code} {msg}")
            try:
                session.ctrl_writer.write(f"{code} {msg}\r\n")
                await session.ctrl_writer.drain()
            except OSError:  # Connection closed unexpectedly.
                success = False
        elif isinstance(msg, list):  # multi-line, dashes after code
            for line in range(len(msg)):
                self.debug(f"{code}-{msg[line]}")
                try:
                    session.ctrl_writer.write(f"{code}-{msg[line]}\r\n")
                except OSError:
                    success = False
                    break
            self.debug(f"{code} End.")
            try:
                session.ctrl_writer.write(f"{code} End.\r\n")  # last line, no dash
                await session.ctrl_writer.drain()
            except OSError:
                success = False
        return success

    # Each command function below returns a boolean to indicate if session
    # should be maintained (True) or ended (False.) Most return True.

    async def mode(self, session, param):
        """
        This server (and most others) only supports stream mode. RFC-959

        Args:
            param (string): single character to indicate transfer mode

        Returns: True
        """
        if param.upper() == "S":
            await self.send_response(session, 200, "OK.")
        else:
            await self.send_response(session, 504, "Transfer mode not supported.")
        return True

    async def noop(self, session, _):
        """
        Do nothing. Used by some clients to stop the connection from timing out.
        RFC-959

        Args:
            session (object): the FTP client's login session info
            _ (discard): command does not take parameters

        Returns: True
        """
        await self.send_response(session, 200, "Take your time. I'll wait.")
        return True

    async def passwd(self, session, password):
        """
        Verify user credentials and drop the connection if incorrect. RFC-959

        Args:
            pass_response (string): the cleartext password
            session (object): the FTP client's login session info

        Returns:
            boolean: True if login succeeded, False if not
        """
        uid = None
        authenticated = False

        # First, find the user entry.
        for i in range(len(self._accounts)):
            if self._accounts[i].startswith(session.username + ":"):
                uid = i
                self.debug(f"Found user account for: {session.username} (uid={uid})")
                break
        if uid is not None:
            stored_password = self._accounts[uid].split(":")[1]
            if stored_password.startswith("$"):
                self.debug(f"Authenticating against hashed password: {stored_password}")
                authenticated = SHA256AES.verify_passwd_entry(stored_password, password)
            else:
                self.debug("Authenticating against cleartext password: ********")
                authenticated = (stored_password == password)
        if not authenticated:
            await sleep_ms(1000)  # throttle repeated bad attempts
            await self.send_response(session, 430, "Invalid username or password.")
            return False
        else:
            session.uid = uid
            await self.send_response(
                session, 230, f"User {session.username} logged in."
            )
            return True

    async def pasv(self, session, _):
        """
        Start a new data listener on one of the high numbered ports and
        report back to the client. RFC-959

        Args:
            session (object): the FTP client's login session info
            _ (discard): command does not take parameters

        Returns:
            boolean: True
        """
        host_octets = self._host.replace(".", ",")
        port = self.get_pasv_port()
        port_octet_high = port // 256
        port_octet_low = port % 256
        self.debug(f"Starting data listener on port: {self._host}:{port}")
        session.data_listener = await start_server(
            self.on_data_connect, self._host, port, 1
        )
        await self.send_response(
            session,
            227,
            f"Entering passive mode. ({host_octets},{port_octet_high},{port_octet_low})",
        )
        return True

    async def port(self, session, address):
        """
        Open a connection to the FTP client at the specified address/port.

        Args:
            session (object): the FTP client's login session info
            address (string): comma-separated octets as specified in RFC-959
        Returns:
            boolean: True
        """
        self.debug(f"Port address: {address}")
        if address.count(",") != 5:
            await self.send_response(session, 451, "Invalid parameter.")
        else:
            a = address.split(",")
            host = f"{a[0]}.{a[1]}.{a[2]}.{a[3]}"
            port = int(a[4]) * 256 + int(a[5])
            self.debug(f"Opening data connection to: {host}:{port}")
            try:
                (
                    session.data_reader,
                    session.data_writer,
                ) = await open_connection(host, port)
            except OSError:
                await self.send_response(
                    session, 425, "Could not open data connection."
                )
            else:
                await self.send_response(session, 200, "PORT command successful.")
        return True

    async def quit(self, session, _):
        """
        User sign off. Returning False signals exit by the control channel loop.
        RFC-959

        Args:
            session (object): the FTP client's login session info
            _ (discard): command does not take parameters

        Returns: False
        """
        await self.send_response(session, 221, f"Bye, {session.username}.")
        return False

    async def retr(self, session, filepath):
        """
        Given a file path, retrieve the file from flash ram and send it to
        the client over the pre-established data connection. RFC-959

        Args:
            session (object): the FTP client's login session info
            file (string): a path indicating the file resource

        Returns:
            boolean: True
        """
        if not filepath:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            filepath = FTPdLite.decode_path(session, filepath)
            try:
                stat(filepath)
            except OSError:
                await self.send_response(session, 550, FTPdLite.ENOENT)
            else:
                if await self.verify_data_connection(session) is False:
                    await self.send_response(
                        session, 426, "Data connection closed. Transfer aborted."
                    )
                else:
                    await self.send_response(session, 150, "Transferring file.")
                    try:
                        with open(filepath, "rb") as file:
                            for chunk in FTPdLite.read_file_chunk(file):
                                session.data_writer.write(chunk)
                                await session.data_writer.drain()
                    except OSError:
                        await self.send_response(session, 451, "Error reading file.")
                    else:
                        await self.send_response(session, 226, "Transfer finished.")
                        await self.close_data_connection(session)
        return True

    async def stor(self, session, filepath):
        """
        Given a file path, open a data connection and write the incoming
        stream data to the file. RFC-959
        """
        if not filepath:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            filepath = FTPdLite.decode_path(session, filepath)
            if session.has_write_access(filepath) is False:
                await self.send_response(session, 550, FTPdLite.EACCES)
            else:
                if await self.verify_data_connection(session) is False:
                    await self.send_response(
                        session, 426, "Data connection closed. Transfer aborted."
                    )
                else:
                    await self.send_response(session, 150, "Transferring file.")
                    try:
                        with open(filepath, "wb") as file:
                            while True:
                                chunk = await session.data_reader.read(512)
                                if chunk:
                                    file.write(chunk)
                                else:
                                    break
                    except OSError:
                        await self.send_response(session, 451, "Error writing file.")
                    else:
                        await self.send_response(session, 226, "Transfer finished.")
                        await self.close_data_connection(session)
        return True

    async def stru(self, session, param):
        """
        Obsolete, but included for compatibility. RFC-959

        Args:
            session (object): the FTP client's login session info
            param (string): single character to indicate file structure

        Returns: True
        """
        if param.upper() == "F":
            await self.send_response(session, 200, "OK.")
        else:
            await self.send_response(session, 504, "Structure not supported.")
        return True

    async def type(self, session, type):
        """
        TYPE is implemented to satisfy some clients, but doesn't actually
        do anything to change the translation of end-of-line characters
        for this server. RFC-959
        """
        if type.upper() in ("A", "A N", "I", "L 8"):
            await self.send_response(session, 200, "Always in binary mode.")
        else:
            await self.send_response(session, 504, "Invalid type.")
        return True

    async def user(self, session, username):
        """
        Record the username and let client know if a password is required.
        RFC-959

        Args:
            username (string): the USER presented at the login prompt
            session (object): info about the client session, including streams

        Returns: True
        """
        session.username = username
        if self._accounts != []:
            await self.send_response(session, 331, f"Password required for {username}.")
        else:
            await self.send_response(session, 230, f"User {username} logged in.")
            try:
                admin_user = self._accounts[0].split(":")[0]
            except IndexError:
                admin_user = "root"
            if username == admin_user:
                self.debug(f"User {username} has admin privileges.")
                session.uid = 0
        return True

    # Connection handlers

    async def verify_data_connection(self, session):
        """
        Ensure the data connection is ready before data is sent

        Args:
            session (object): info about the client session, including streams

        Returns:
            boolean: True if connction is ready, False if not
        """
        try:
            session.data_reader
            session.data_writer  # should exist when data connection is up
        except AttributeError:
            await sleep_ms(200)  # if not, wait and try again
        try:
            session.data_reader
            session.data_writer
        except AttributeError:
            return False
        else:
            return True

    def get_pasv_port(self):
        """
        Get a TCP port number from the pool, then rotate the list to ensure
        it won't be used again for a while. Helps avoid address in use error.

        Returns:
            integer: TCP port number
        """
        port = self._pasv_port_pool.pop(0)
        self._pasv_port_pool.append(port)
        return port

    async def close_data_connection(self, session):
        """
        Close data connection streams and remove them from the session.

        Args:
            session (object): info about the client session, including streams
        """
        self.debug("Closing data connection...")
        try:
            session.data_writer
        except AttributeError:
            self.debug("No data writer stream exists to be closed.")
        else:
            session.data_writer.close()
            await session.data_writer.wait_closed()
            del session.data_writer
        try:
            session.data_reader
        except AttributeError:
            self.debug("No data reader stream exists to be closed.")
        else:
            session.data_reader.close()
            await session.data_reader.wait_closed()
            del session.data_reader
        try:
            session.data_listener
        except AttributeError:
            self.debug("No data listener object exists to be closed.")
        else:
            session.data_listener.close()
            await session.data_listener.wait_closed()
            del session.data_listener
        self.debug("Data connection closed.")

    async def on_data_connect(self, data_reader, data_writer):
        """
        Handler for PASV data connections. Remember the streams for later commands.

        Args:
            data_reader (stream): files uploaded from the client
            data_writer (stream): files/data requested by the client
        """
        client_ip, client_port = data_writer.get_extra_info("peername")
        self.debug(f"Data connection from: {client_ip}:{client_port}")
        found_sessions = await self.find_session(client_ip)
        if len(found_sessions) != 1:  # should be only one per IP
            print(f"ERROR: Multiple sessions found for {client_ip}")
        else:
            session = found_sessions[0]
            session.data_reader = data_reader
            session.data_writer = data_writer
            self.debug(f"session.data_reader = {session.data_reader}")
            self.debug(f"session.data_writer = {session.data_writer}")

    async def close_ctrl_connection(self, session):
        """
        Close the control channel streams.

        Args:
            session (object): info about the client session, including streams
        """
        session.ctrl_writer.close()
        await session.ctrl_writer.wait_closed()
        session.ctrl_reader.close()
        await session.ctrl_reader.wait_closed()
        self.debug(f"Control connection closed for: {session.client_ip}")

    async def on_ctrl_connect(self, ctrl_reader, ctrl_writer):
        """
        Handler for control connection. Parses commands to carry out actions.

        Args:
            ctrl_reader (stream): incoming commands from the client
            ctrl_writer (stream): replies from the server to the client
        """
        client_ip, client_port = ctrl_writer.get_extra_info("peername")
        print(f"INFO: Connection from client: {client_ip}:{client_port}")
        session = Session(client_ip, client_port, ctrl_reader, ctrl_writer)
        if (
            len(self._session_list) > self.max_connections
            or await self.find_session(client_ip) != []
        ):
            await self.send_response(session, 421, "Too many connections.")
            del session
        else:
            self._session_list.append(session)
            await self.send_response(session, 220, self._server_name)
            while session:
                try:
                    request = await ctrl_reader.read(self.request_buffer_size)
                except OSError:  # Unexpected disconnection.
                    print(
                        f"Control connection closed for: {session.username}@{session.client_ip}"
                    )
                    del session
                    break
                else:
                    verb, param = self.parse_request(request)
                    try:
                        func = self._ftp_cmd_dict[verb]
                    except KeyError:
                        await self.send_response(
                            session, 502, "Command not implemented."
                        )
                    else:
                        continue_session = await func(session, param)
                        if continue_session is False:
                            await self.close_ctrl_connection(session)
                            print(
                                f"INFO: Session disconnected: {session.username}@{session.client_ip}"
                            )
                            await self.delete_session(session)
                            del session
                            break

    def run(self, loop=None):
        now = time()
        jan_1_2023 = 725846400  # mktime((2023, 1, 1, 0, 0, 0, 0, 1))
        if now < jan_1_2023:
            print("WARNING: System clock not set. File timestamps will be incorrect.")
        if loop is None:
            loop = get_event_loop()
        server = start_server(self.on_ctrl_connect, self._host, self._port, 5)
        loop.create_task(server)
        print(f"Listening on {self._host}:{self._port}")
        loop.run_forever()


class FTPd(FTPdLite):
    """
    A more complete RFC-959 FTP server implementation.
    """

    def __init__(
        self,
        host="127.0.0.1",
        port=21,
        server_name="FTPdLite (MicroPython)",
        pasv_port_range=range(49152, 49407),
    ):
        super().__init__(host, port, server_name, pasv_port_range)
        self._ftp_cmd_dict.update(
            {
                "ALLO": self.noop,
                "CDUP": self.cdup,
                "CWD": self.cwd,
                "DELE": self.dele,
                "EPSV": self.epsv,
                "FEAT": self.feat,
                "HELP": self.help,
                "LIST": self.list,
                "MKD": self.mkd,
                "MODE": self.mode,
                "NLST": self.nlst,
                "OPTS": self.opts,
                "PWD": self.pwd,
                "RMD": self.rmd,
                "RNFR": self.rnfr,
                "RNTO": self.rnto,
                "SITE": self.site,
                "SIZE": self.size,
                "STAT": self.stat,
                "SYST": self.syst,
                "XCUP": self.cdup,
                "XCWD": self.cwd,
                "XMKD": self.mkd,
                "XPWD": self.pwd,
                "XRMD": self.rmd,
            }
        )
        self._site_cmd_dict = {
            "df": self.site_df,
            "free": self.site_free,
            "gc": self.site_gc,
            "hashpass": self.site_hashpass,
            "help": self.site_help,
            "kick": self.site_kick,
            "shutdown": self.site_shutdown,
            "uptime": self.site_uptime,
            "who": self.site_who,
        }

    @staticmethod
    def date_format(timestamp):
        """
        Turn seconds past the epoch into a human readable date/time to be
        used in Unix-style directory listings.

        Args:
            timestamp (integer): number of seconds past the Python epoch

        Returns:
            string: date and time suitable for `ls -l` output.
        """
        months = [
            "",
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        datetime = localtime(timestamp)
        mon = months[datetime[1]]
        day = datetime[2]
        day_pad = " " if day < 10 else ""
        year = datetime[0]
        hour = datetime[3]
        hour_pad = "0" if hour < 10 else ""
        min = datetime[4]
        min_pad = "0" if min < 10 else ""
        now = time()
        one_year = 31536000

        if now - timestamp < one_year:
            output = f"{mon} {day_pad}{day} {hour_pad}{hour}:{min_pad}{min}"
        else:
            output = f"{mon} {day_pad}{day}  {year}"
        return output

    @staticmethod
    def human_readable(byte_size):
        if byte_size > 1073741824:
            size = byte_size / 1073741824
            human_readable = f"{size:.2f}G"
        elif byte_size > 1048576:
            size = byte_size / 1048576
            human_readable = f"{size:.2f}M"
        elif byte_size > 1024:
            size = byte_size / 1024
            human_readable = f"{size:.2f}K"
        else:
            size = byte_size
            human_readable = f"{size:d}"
        return human_readable

    def add_account(self, acct_entry):
        """
        Given a username:password entry in the style of Apache htpasswd or
        Unix-style /etc/passwd entry, add the account to the list accepted
        by this server.

        Args:
            acct_entry (string): htpasswd style 'username:password'

        Returns:
            True if acct_entry format was acceptable, False if not.
        """
        if acct_entry.count(":") == 1:
            self._accounts.append(acct_entry)
            return True
        else:
            print("ERROR: Invalid account info string.")
            return False

    # Additional FTP commands

    async def cdup(self, session, _):
        """
        Go up a directory level (just like `cd ..` would do.)
        RFC-959 specifies as CDUP, RFC-775 specifies as XCUP

        Args:
            session (object): the FTP client's login session info
            _ (discard): does not take parameters

        Returns:
            boolean: True
        """
        session.cwd = session.cwd.rsplit("/", 1)[0] or "/"
        await self.send_response(session, 250, session.cwd)
        return True

    async def cwd(self, session, dirpath):
        """
        Change working directory.
        RFC-959 specifies as CWD, RFC-775 specifies as XCwD

        Args:
            session (object): the FTP client's login session info
            dirpath (string): a path indicating a directory resource

        Returns:
            boolean: True
        """
        dirpath = FTPd.decode_path(session, dirpath)
        try:
            properties = stat(dirpath)
        except OSError:
            await self.send_response(session, 550, FTPd.ENOENT)
        else:
            if not properties[0] & 0x4000:
                await self.send_response(session, 550, "Not a directory.")
            else:
                session.cwd = dirpath
                await self.send_response(
                    session, 250, f"Working directory is now: {session.cwd}"
                )
        return True

    async def dele(self, session, filepath):
        """
        Given a path, delete the file. RFC-959

        Args:
            session (object): the FTP client's login session info
            filepath (string): a path indicating a file resource

        Returns:
            boolean: True
        """
        if not filepath:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            filepath = FTPd.decode_path(session, filepath)
            if session.has_write_access(filepath) is False:
                await self.send_response(session, 550, FTPd.EACCES)
            else:
                try:
                    remove(filepath)
                except OSError:
                    await self.send_response(session, 550, FTPd.ENOENT)
                else:
                    await self.send_response(session, 250, "OK.")
        return True

    async def epsv(self, session, _):
        """
        Start a new data listener on one of the high numbered ports and
        report back to the client. Similar to PASV, but with a different
        response format. RFC-2428

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: True
        """
        port = self.get_pasv_port()
        self.debug(f"Starting data listener on port: {port}")
        session.data_listener = await start_server(
            self.on_data_connect, self._host, port, 1
        )
        await self.send_response(
            session, 229, f"Entering extended passive mode. (|||{port}|)"
        )
        return True

    async def feat(self, session, _):
        """
        Reply with multi-line list of extra capabilities. RFC-2389

        Args:
            _ (discard): does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: True
        """
        feat_output = [
            "Extensions supported:\r\n EPSV\r\n PASV\r\n SIZE\r\n UTF8"
        ]
        await self.send_response(session, 211, feat_output)

    async def help(self, session, _):
        """
        Reply with help only in a general sense, not per individual command.
        RFC-959

        Args:
            session (object): the FTP client's login session info
            _ (discard): this server does not support specific help topics

        Returns:
            boolean: True
        """
        commands = sorted(list(self._ftp_cmd_dict.keys()))
        help_output = ["Available FTP commands:"]
        line = ""
        for i in range(len(commands)):
            line += f"  {commands[i]:4s}"
            if (i + 1) % 10 == 0:
                help_output.append(line)
                line = ""
        help_output.append(line)
        await self.send_response(session, 214, help_output)
        return True

    async def list(self, session, dirpath):
        """
        Send a Linux style directory listing, though ownership and permission
        has no meaning in the flash filesystem. RFC-959

        Args:
            session (object): the FTP client's login session info
            dirpath (string): a path indicating a directory resource

        Returns:
            boolean: True
        """
        dirpath = FTPd.decode_path(session, dirpath)
        try:
            dir_entries = sorted(listdir(dirpath))
        except OSError:
            await self.send_response(session, 451, "Unable to read directory.")
        else:
            if await self.verify_data_connection(session) is False:
                await self.send_response(
                    session, 426, "Data connection closed. Transfer aborted."
                )
            else:
                await self.send_response(session, 150, f"Contents of: {dirpath}")
                for entry in dir_entries:
                    self.debug(
                        f"Fetching properties of: {FTPd.path_join(dirpath, entry)}"
                    )
                    properties = stat(FTPd.path_join(dirpath, entry))
                    if properties[0] & 0x4000:  # entry is a directory
                        permissions = "drwxrwxr-x"
                        size = "0"
                        entry += "/"
                    else:
                        permissions = "-rw-rw-r--"
                        size = FTPd.human_readable(properties[6])
                    uid = "root" if properties[4] == 0 else properties[4]
                    gid = "root" if properties[5] == 0 else properties[5]
                    mtime = FTPd.date_format(properties[8])
                    formatted_entry = f"{permissions}  1  {uid:4}  {gid:4}  {size:>10s}  {mtime:>11s}  {entry}"
                    session.data_writer.write(formatted_entry + "\r\n")
                await session.data_writer.drain()
                await self.send_response(session, 226, "Directory list sent.")
                await self.close_data_connection(session)
        return True

    async def mkd(self, session, dirpath):
        """
        Given a path, create a new directory.
        RFC-959 specifies MKD, RFC-775 specifies XMKD

        Args:
            session (object): the FTP client's login session info
            dirpath (string): a path indicating the directory resource

        Returns:
            boolean: True
        """
        if not dirpath:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            dirpath = FTPd.decode_path(session, dirpath)
            if session.has_write_access(dirpath) is False:
                await self.send_response(session, 550, FTPd.EACCES)
            else:
                try:
                    mkdir(dirpath)
                    await self.send_response(
                        session, 257, f'"{dirpath}" directory created.'
                    )
                except OSError:
                    await self.send_response(
                        session, 550, "Failed to create directory."
                    )
        return True

    async def mode(self, session, param):
        """
        This server (and most others) only supports stream mode. RFC-959

        Args:
            param (string): single character to indicate transfer mode

        Returns:
            boolean: True
        """
        if param.upper() == "S":
            await self.send_response(session, 200, "OK.")
        else:
            await self.send_response(session, 504, "Transfer mode not supported.")
        return True

    async def nlst(self, session, dirpath):
        """
        Send a list of file names only, without the extra information.
        RFC-959

        Args:
            session (object): the FTP client's login session info
            dirpath (string): a path indicating a directory resource

        Returns:
            boolean: True
        """
        dirpath = FTPd.decode_path(session, dirpath)
        try:
            dir_entries = sorted(listdir(dirpath))
        except OSError:
            await self.send_response(session, 451, "Unable to read directory.")
        else:
            if await self.verify_data_connection(session) is False:
                await self.send_response(
                    session, 426, "Data connection closed. Transfer aborted."
                )
            else:
                await self.send_response(session, 150, f"Contents of: {dirpath}")
                try:
                    session.data_writer.write("\r\n".join(dir_entries) + "\r\n")
                except OSError:
                    self.send_response(
                        session, 426, "Data connection closed. Transfer aborted."
                    )
                else:
                    await session.data_writer.drain()
                    await self.send_response(session, 226, "Directory list sent.")
                    await self.close_data_connection(session)
        return True

    async def opts(self, session, option):
        """
        Reply to the common case of UTF-8, but nothing else. RFC-2389

        Args:
            option (string): the option and its value
            session (object): the FTP client's login session info

        Returns:
            boolean: True
        """
        if option.upper() == "UTF8 ON":
            await self.send_response(session, 200, "Always in UTF8 mode.")
        else:
            await self.send_response(session, 501, "Unknown option.")
        return True

    async def pwd(self, session, _):
        """
        Report back with the current working directory.
        RFC-959 specifies as PWD, RFC-775 specifies as XPWD

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: True
        """
        await self.send_response(session, 257, f'"{session.cwd}"')
        return True

    async def rnfr(self, session, rnfr_path):
        """
        Given a file path, store it in preparation for a rename operation.
        RFC-959

        Args:
            session (object): the FTP client's login session info
            rnfr_path (string): source path of the rename operation

        Returns:
            boolean: True
        """
        if not rnfr_path:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            rnfr_path = FTPd.decode_path(session, rnfr_path)
            try:
                stat(rnfr_path)
            except OSError:
                await self.send_response(session, 550, FTPd.ENOENT)
            else:
                session._rnfr_path = rnfr_path
                await self.send_response(session, 350, "RNFR accepted.")
        return True

    async def rnto(self, session, rnto_path):
        """
        Given a destination file path, complete the rename operation. RFC-959

        Args:
            session (object): the FTP client's login session info
            rnto_path (string): destination path of the rename operation

        Returns:
            boolean: True
        """
        if not rnto_path:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            rnto_path = FTPd.decode_path(session, rnto_path)
            if session.has_write_access(rnto_path) is False:
                await self.send_response(session, 550, FTPd.EACCES)
            else:
                try:
                    rename(session._rnfr_path, rnto_path)
                except (AttributeError, OSError):
                    await self.send_response(session, 550, "Rename failed.")
                else:
                    await self.send_response(
                        session, 250, f'Renamed "{session._rnfr_path}" to "{rnto_path}"'
                    )
                del session._rnfr_path
        return True

    async def rmd(self, session, dirpath):
        """
        Given a directory path, remove the directory. Must be empty.
        RFC-959 specifies as RKD, RFC-775 specifies as XRKD
        """
        if not dirpath:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            dirpath = FTPd.decode_path(session, dirpath)
            if session.has_write_access(dirpath) is False:
                await self.send_response(session, 550, FTPd.EACCES)
            else:
                dirpath = FTPd.decode_path(session, dirpath)
                try:
                    rmdir(dirpath)
                except OSError:
                    await self.send_response(
                        session, 550, "No such directory or directory not empty."
                    )
                else:
                    await self.send_response(session, 250, "OK.")
        return True

    async def site(self, session, cmdline):
        """
        RFC-959 specifies SITE as a way to access services not defined
        in the common set of FTP commands. This server offers several
        Unix-style commands as well as a few MicroPython-specific ones.
        """
        if " " in cmdline:
            site_cmd = cmdline.split(None, 1)[0].lower()
            site_param = cmdline.split(None, 1)[1]
        else:
            site_cmd = cmdline.lower()
            site_param = ""
        try:
            func = self._site_cmd_dict[site_cmd]
        except KeyError:
            await self.send_response(session, 504, "Parameter not supported.")
        else:
            status, output = await func(session, site_param)
            await self.send_response(session, status, output)
        return True

    async def size(self, session, filepath):
        """
        Given a file path, reply with the number of bytes in the file.
        Defined in RFC-3659.
        """
        if not filepath:
            await self.send_response(session, 501, "Missing parameter.")
        else:
            filepath = FTPd.decode_path(session, filepath)
            try:
                size = stat(filepath)[6]
            except OSError:
                await self.send_response(session, 550, FTPd.ENOENT)
            else:
                await self.send_response(session, 213, f"{size}")
        return True

    async def stat(self, session, pathname):
        """
        Report sytem status or existence of file/dir. RFC-959

        Args:
            pathname (string): path to a file or directory

        Returns:
            boolean: True
        """
        if pathname is None or pathname == "":
            server_status = [
                f"{self._server_name}",
                f"Logged in as: {session.username}",
                "TYPE: L8, FORM: Nonprint; STRUcture: File; transfer MODE: Stream"
            ]
            await self.send_response(session, 211, server_status)
        else:
            try:
                properties = stat(pathname)
            except OSError:
                await self.send_response(session, 550, FTPd.ENOENT)
            else:
                if properties[0] & 0x4000:  # entry is a directory
                    await self.send_response(session, 213, f"{pathname}")
                else:
                    await self.send_response(session, 211, f"{pathname}")
        return True

    async def syst(self, session, _):
        """
        Reply to indicate this server follows Unix conventions. RFC-959
        """
        await self.send_response(session, 215, "UNIX Type: L8")
        return True

    # Administrative commands

    async def site_df(self, session, filesystem):
        filesystem = filesystem or "/"
        try:
            properties = statvfs(filesystem)
        except OSError:
            return 501, "Invalid filesystem."
        else:
            fragment_size = properties[1]
            blocks_total = properties[2]
            blocks_available = properties[4]
            size = int(blocks_total * fragment_size)
            size_hr = FTPd.human_readable(size)
            avail = int(blocks_available * fragment_size)
            avail_hr = FTPd.human_readable(avail)
            used = size - avail
            used_hr = FTPd.human_readable(used)
            percent_used = round(100 * used / size)
            output = [
                "Filesystem        Size        Used       Avail      Use%",
                f"{filesystem:12s}  {size_hr:>8s}    {used_hr:>8s}    {avail_hr:>8s}      {percent_used:3d}%"
            ]
        return 211, output

    async def site_free(self, session, _):
        free = FTPd.human_readable(mem_free())
        used = FTPd.human_readable(mem_alloc())
        total = FTPd.human_readable(mem_free() + mem_alloc())
        output = [
            "         Total       Used      Avail",
            f"Mem: {total:>9s}  {used:>9s}  {free:>9s}"
        ]
        return 211, output

    async def site_gc(self, session, _):
        before = mem_free()
        gc_collect()
        after = mem_free()
        regained = FTPd.human_readable(after - before)
        return 211, f"Additional {regained} available."

    async def site_hashpass(self, session, cleartext):
        if not cleartext:
            return 501, "Usage: hashpass <cleartext password>"
        else:
            return 211, SHA256AES.create_passwd_entry(cleartext)

    async def site_help(self, session, _):
        commands = sorted(list(self._site_cmd_dict.keys()))
        help_output = ["Available commands:"]
        line = ""
        for i in range(len(commands)):
            line += f"  {commands[i]:9s}"
            if (i + 1) % 5 == 0:
                help_output.append(line)
                line = ""
        help_output.append(line)
        return 214, help_output

    async def site_kick(self, session, lookup):
        if session.uid != 0:
            return 550, "Not authorized."
        if not lookup:
            return 501, "Usage: kick <username> or kick <ip address>"
        matching_sessions = await self.find_session(lookup)
        self.debug(f"Found {len(matching_sessions)} sessions for {lookup}")
        if len(matching_sessions) < 1:
            return 450, "Not found."
        elif len(matching_sessions) > 1:
            return 450, f"Multiple instances of {lookup} exist."
        else:
            print(
                f"INFO: Kicking session: {matching_sessions[0].username}@{matching_sessions[0].client_ip}"
            )
            await self.delete_session(matching_sessions[0])
            return 211, f"Kicked {lookup}"

    async def site_shutdown(self, session, param):
        if session.uid != 0:
            return 550, "Not authorized."
        sync()
        await sleep_ms(1000)
        sync()
        if param == "-h":
            print("Server going down for deep sleep.")
            await sleep_ms(1000)
            deepsleep()
        elif param == "-r":
            print("Server going down for reboot.")
            await sleep_ms(1000)
            reset()
        else:
            return 501, "Usage: shutdown -h (halt) or shutdown -r (reboot)"

    async def site_uptime(self, session, _):
        seconds = time() - self._start_time
        days = seconds // 86400
        seconds = seconds % 86400
        hours = seconds // 3600
        seconds = seconds % 3600
        mins = seconds // 60
        mins_pad = "0" if mins < 10 else ""
        now = FTPd.date_format(time())
        return 211, f"{now} up {days} days, {hours}:{mins_pad}{mins}, {len(self._session_list)} users"

    async def site_who(self, session, _):
        user_width = 0
        addr_width = 0
        output = ["Current FTP users:"]
        for s in self._session_list:
            user_width = max(user_width, len(s.username))
            addr_width = max(addr_width, len(s.client_ip))
        for s in self._session_list:
            login_time = FTPd.date_format(s.login_time)
            output.append(
                f"{s.username:{user_width}s}  {s.client_ip:{addr_width}s}  {login_time}"
            )
        return 211, output
