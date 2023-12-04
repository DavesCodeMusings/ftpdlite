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
from os import getcwd, listdir, mkdir, remove, rmdir, stat, statvfs, sync
from time import localtime, mktime, time
from network import hostname
from socket import getaddrinfo, AF_INET
from gc import collect as gc_collect, mem_alloc, mem_free
from machine import deepsleep, reset
from random import choice, seed
from cryptolib import aes
from hashlib import sha256
from binascii import b2a_base64


class Session:
    """
    An interactive connection from a client.
    """

    def __init__(self, client_ip, client_port, ctrl_reader, ctrl_writer):
        self._accepting_connections = False
        self._client_ip = client_ip
        self._client_port = client_port
        self._ctrl_reader = ctrl_reader
        self._ctrl_writer = ctrl_writer
        self._username = "nobody"
        self._uid = 65534
        self._gid = 65534
        self._home_dir = "/"
        self._working_dir = getcwd()
        self._login_time = time()
        self._last_active_time = time()

    @property
    def client_ip(self):
        return self._client_ip

    @property
    def client_port(self):
        return self._client_port

    @property
    def ctrl_reader(self):
        return self._ctrl_reader

    @property
    def ctrl_writer(self):
        return self._ctrl_writer

    @property
    def data_reader(self):
        return self._data_reader

    @data_reader.setter
    def data_reader(self, stream):
        self._data_reader = stream

    @data_reader.deleter
    def data_reader(self):
        del self._data_reader

    @property
    def data_writer(self):
        return self._data_writer

    @data_writer.setter
    def data_writer(self, stream):
        self._data_writer = stream

    @data_writer.deleter
    def data_writer(self):
        del self._data_writer

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, username):
        self._username = username

    @property
    def uid(self):
        return self._uid

    @uid.setter
    def uid(self, uid):
        self._uid = uid

    @property
    def gid(self):
        return self._gid

    @gid.setter
    def gid(self, gid):
        self._gid = gid

    @property
    def home(self):
        return self._home_dir

    @property
    def cwd(self):
        return self._working_dir

    @cwd.setter
    def cwd(self, dirpath):
        self._working_dir = dirpath

    @property
    def login_time(self):
        return self._login_time

    @property
    def last_active_time(self):
        return self._last_active_time

    @last_active_time.setter
    def last_active_time(self, time):
        self._last_active_time = time

    def has_write_access(self, path):
        """
        Given a file or directory path, report if writing by the user is allowed.

        Args:
            path: the absolute file or directory path to verify

        Returns:
            boolean: True if writable by the user, false if not
        """
        if self.uid == 0 or self.gid == 10:  # root user or wheel group
            return True
        elif self.uid >= 65534 or self.gid >= 65534:  # nobody user, group
            return False
        elif self.home and path.startswith(self.home):
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
    A minimalist FTP server for MicroPython.
    """

    def __init__(
        self,
        pasv_port_range=range(49152, 49407),
        request_buffer_size=512,
        server_name="FTPdLite (MicroPython)",
    ):
        self._credentials = []
        self._pasv_port_pool = list(pasv_port_range)
        self._request_buffer_size = request_buffer_size
        self._server_name = server_name
        self._start_time = time()
        self._session_list = []
        self._ftp_cmd_dict = {
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
            "NOOP": self.noop,
            "OPTS": self.opts,
            "PASS": self.passwd,
            "PASV": self.pasv,
            "PORT": self.port,
            "PWD": self.pwd,
            "RMD": self.rmd,
            "QUIT": self.quit,
            "RETR": self.retr,
            "SITE": self.site,
            "SIZE": self.size,
            "STAT": self.stat,
            "STOR": self.stor,
            "STRU": self.stru,
            "SYST": self.syst,
            "TYPE": self.type,
            "USER": self.user,
            "XCUP": self.cdup,
            "XCWD": self.cwd,
            "XMKD": self.mkd,
            "XPWD": self.pwd,
            "XRMD": self.rmd,
        }

        self._site_cmd_dict = {
            "date": self.site_date,
            "df": self.site_df,
            "free": self.site_free,
            "gc": self.site_gc,
            "help": self.site_help,
            "kick": self.site_kick,
            "shutdown": self.site_shutdown,
            "uptime": self.site_uptime,
            "who": self.site_who,
            "whoami": self.site_whoami,
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
    def decode_path(path, session):
        """
        Given a file or directory path, expand it to an absolute path.

        Args:
            path (string): a relative, absolute, or empty path to a resource
            session (object): the FTP client's session with cwd and home dir

        Returns:
            string: an absolute path to the resource
        """
        if path is None or path.startswith("-"):
            absolute_path = session.cwd  # client sent a command-line option, do nothing
        else:
            if path.startswith("~"):
                path = path.replace("~", session.home)
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

    @staticmethod
    def path_join(*args):
        """
        There's no os.path.join available in MicroPython, so...

        Args:
            *args (string): a variable number of path components

        Returns:
            string: the resulting absolute path
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

    def add_credential(self, credential):
        """
        Given a username/password entry in the style of Apache htpasswd or
        Unix /etc/passwd, add the credential to the list accepted by this
        server.

        Args:
            credential (string): either 'username:password' or the Unix-
                style 'username:password:uid:gid:gecos:home:shell'

        Returns:
            True if credential format was acceptable, False if not.
        """
        if credential.count(":") == 6:
            self._credentials.append(credential)
        elif credential.count(":") == 1:
            credential += ":65534:65534:::/bin/nologin"
            self._credentials.append(credential)
            return True
        else:
            print("ERROR: Invalid credential string.")
            return False

    def debug(self, msg):
        if self._debug:
            print("DEBUG:", msg)

    async def delete_session(self, session):
        """
        Given a session object, delete it from the server's session list.

        Args:
            session (object): the client session of interest

        Returns: nothing
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

    def parse_request(self, req_buffer):
        """
        Given a line of input, split the command into a verb and parameter.

        Args:
            req_buffer (bytes): the unprocessed request from the client

        Returns:
            verb, param (tuple): action and related parameter string
        """
        try:
            request = req_buffer.decode("utf-8").rstrip("\r\n")
        except OSError:
            request = None
        if request is None or len(request) == 0:
            verb = "QUIT"  # Filezilla doesn't send QUIT, just NULL.
            param = None
            self.debug("Received NULL command. Interpreting as QUIT.")
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

    async def send_response(self, code, msg, writer):
        """
        Given a status code and a message, send a response to the client.

        Args:
            code (integer): a three digit status code
            msg (string or list): a single-line (string) or multi-line (list)
                human readable message describing the result
            writer (stream): the FTP client's control connection

        Returns:
            boolean: True if stream writer was up, false if not
        """
        success = True
        if isinstance(msg, str):  # single line
            self.debug(f"{code} {msg}")
            try:
                writer.write(f"{code} {msg}\r\n")
                await writer.drain()
            except OSError:  # Connection closed unexpectedly.
                success = False
        elif isinstance(msg, list):  # multi-line, dashes after code
            for line in range(len(msg) - 1):
                self.debug(f"{code}-{msg[line]}")
                try:
                    writer.write(f"{code}-{msg[line]}\r\n")
                except OSError:
                    success = False
                    break
            self.debug(f"{code} {msg[-1]}")
            try:
                writer.write(f"{code} {msg[-1]}\r\n")  # last line, no dash
                await writer.drain()
            except OSError:
                success = False
        return success

    # Each command function below returns a boolean to indicate if session
    # should be maintained (True) or ended (False.) Most return True.

    async def cdup(self, _, session):
        """
        Go up a directory level (just like `cd ..` would do.)
        RFC-959 specifies as CDUP, RFC-775 specifies as XCUP

        Args:
            _ (discard): does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        session.cwd = session.cwd.rsplit("/", 1)[0] or "/"
        await self.send_response(250, session.cwd, session.ctrl_writer)
        return True

    async def cwd(self, dirpath, session):
        """
        Change working directory.
        RFC-959 specifies as CWD, RFC-775 specifies as XCwD

        Args:
            dirpath (string): a path indicating a directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        dirpath = FTPdLite.decode_path(dirpath, session)
        try:
            properties = stat(dirpath)
        except OSError:
            await self.send_response(550, "No such directory.", session.ctrl_writer)
        else:
            if not properties[0] & 0x4000:
                await self.send_response(550, "Not a directory.", session.ctrl_writer)
            else:
                session.cwd = dirpath
                await self.send_response(
                    250,
                    f"Working directory is now: {session.cwd}",
                    session.ctrl_writer,
                )
        return True

    async def dele(self, filepath, session):
        """
        Given a path, delete the file. RFC-959

        Args:
            filepath (string): a path indicating a file resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        if not filepath:
            await self.send_response(501, "Missing parameter.", session.ctrl_writer)
        else:
            filepath = FTPdLite.decode_path(filepath, session)
            if session.has_write_access(filepath) is False:
                await self.send_response(550, "No access.", session.ctrl_writer)
            else:
                try:
                    remove(filepath)
                except OSError:
                    await self.send_response(550, "No such file.", session.ctrl_writer)
                else:
                    await self.send_response(250, "OK.", session.ctrl_writer)
        return True

    async def epsv(self, _, session):
        """
        Start a new data listener on one of the high numbered ports and
        report back to the client. Similar to PASV, but with a different
        response format. RFC-2428

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        port = self.get_pasv_port()
        self.debug(f"Starting data listener on port: {port}")
        session.data_listener = await start_server(
            self.on_data_connect, self.host, port, 1
        )
        await self.send_response(
            229, f"Entering extended passive mode. (|||{port}|)", session.ctrl_writer
        )
        return True

    async def feat(self, _, session):
        """
        Reply with multi-line list of extra capabilities. RFC-2389

        Args:
            _ (discard): does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        feat_output = ["Extensions supported:\r\n EPSV\r\n PASV\r\n SIZE", "End."]
        await self.send_response(211, feat_output, session.ctrl_writer)
        return True

    async def help(self, _, session):
        """
        Reply with help only in a general sense, not per individual command.
        RFC-959

        Args:
            _ (discard): this server does not support specific help topics
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        commands = sorted(list(self._ftp_cmd_dict.keys()))
        help_output = ["Available FTP commands:"]
        line = ""
        for c in range(len(commands)):
            line += f"{commands[c]:4s}   "
            if (c + 1) % 9 == 0:
                help_output.append(line)
                line = ""
        help_output.append(line)
        help_output.append("See SITE HELP for extra features.")
        help_output.append("End.")
        await self.send_response(214, help_output, session.ctrl_writer)
        return True

    async def list(self, dirpath, session):
        """
        Send a Linux style directory listing, though ownership and permission
        has no meaning in the flash filesystem. RFC-959

        Args:
            dirpath (string): a path indicating a directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        dirpath = FTPdLite.decode_path(dirpath, session)
        try:
            dir_entries = sorted(listdir(dirpath))
        except OSError:
            await self.send_response(
                451, "Unable to read directory.", session.ctrl_writer
            )
        else:
            if await self.verify_data_connection(session) is False:
                await self.send_response(
                    426,
                    "Data connection closed. Transfer aborted.",
                    session.ctrl_writer,
                )
            else:
                await self.send_response(
                    150, f"Contents of: {dirpath}", session.ctrl_writer
                )
                for entry in dir_entries:
                    self.debug(f"Fetching properties of: {FTPdLite.path_join(dirpath, entry)}")
                    properties = stat(FTPdLite.path_join(dirpath, entry))
                    if properties[0] & 0x4000:  # entry is a directory
                        permissions = "drwxrwxr-x"
                        size = "0"
                        entry += "/"
                    else:
                        permissions = "-rw-rw-r--"
                        size = FTPdLite.human_readable(properties[6])
                    uid = "root" if properties[4] == 0 else properties[4]
                    gid = "root" if properties[5] == 0 else properties[5]
                    mtime = FTPdLite.date_format(properties[8])
                    formatted_entry = f"{permissions}  1  {uid:4}  {gid:4}  {size:>10s}  {mtime:>11s}  {entry}"
                    session.data_writer.write(formatted_entry + "\r\n")
                await session.data_writer.drain()
                await self.send_response(
                    226, "Directory list sent.", session.ctrl_writer
                )
                await self.close_data_connection(session)
        return True

    async def mode(self, param, session):
        """
        This server (and most others) only supports stream mode. RFC-959

        Args:
            param (string): single character to indicate transfer mode

        Returns:
            boolean: always True
        """
        if param.upper() == "S":
            await self.send_response(200, "OK.", session.ctrl_writer)
        else:
            await self.send_response(
                504, "Transfer mode not supported.", session.ctrl_writer
            )
        return True

    async def mkd(self, dirpath, session):
        """
        Given a path, create a new directory.
        RFC-959 specifies MKD, RFC-775 specifies XMKD

        Args:
            dirpath (string): a path indicating the directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        if not dirpath:
            await self.send_response(501, "Missing parameter.", session.ctrl_writer)
        else:
            dirpath = FTPdLite.decode_path(dirpath, session)
            if session.has_write_access(dirpath) is False:
                await self.send_response(550, "No access.", session.ctrl_writer)
            else:
                try:
                    mkdir(dirpath)
                    await self.send_response(
                        257, f'"{dirpath}" directory created.', session.ctrl_writer
                    )
                except OSError:
                    await self.send_response(
                        550, "Failed to create directory.", session.ctrl_writer
                    )
        return True

    async def nlst(self, dirpath, session):
        """
        Send a list of file names only, without the extra information.
        RFC-959

        Args:
            dirpath (string): a path indicating a directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        dirpath = FTPdLite.decode_path(dirpath, session)
        try:
            dir_entries = sorted(listdir(dirpath))
        except OSError:
            await self.send_response(
                451, "Unable to read directory.", session.ctrl_writer
            )
        else:
            if await self.verify_data_connection(session) is False:
                await self.send_response(
                    426,
                    "Data connection closed. Transfer aborted.",
                    session.ctrl_writer,
                )
            else:
                await self.send_response(
                    150, f"Contents of: {dirpath}", session.ctrl_writer
                )
                try:
                    session.data_writer.write("\r\n".join(dir_entries) + "\r\n")
                except OSError:
                    self.send_response(
                        426,
                        "Data connection closed. Transfer aborted.",
                        session.ctrl_writer,
                    )
                else:
                    await session.data_writer.drain()
                    await self.send_response(
                        226, "Directory list sent.", session.ctrl_writer
                    )
                    await self.close_data_connection(session)
        return True

    async def noop(self, _, session):
        """
        Do nothing. Used by some clients to stop the connection from timing out.
        RFC-959

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        await self.send_response(200, "Take your time. I'll wait.", session.ctrl_writer)
        return True

    async def opts(self, option, session):
        """
        Reply to the common case of UTF-8, but nothing else. RFC-2389

        Args:
            option (string): the option and its value
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        if option.upper() == "UTF8 ON":
            await self.send_response(200, "Always in UTF8 mode.", session.ctrl_writer)
        else:
            await self.send_response(501, "Unknown option.", session.ctrl_writer)
        return True

    async def passwd(self, pass_response, session):
        """
        Verify user credentials and drop the connection if incorrect. RFC-959

        Args:
            pass_response (string): the cleartext password
            session (object): the FTP client's login session info

        Returns:
            boolean: True if login succeeded, False if not
        """
        # First, find the user entry.
        for cred in self._credentials:
            if cred.startswith(session.username + ":"):
                self.debug(f"Found user credential for: {session.username}")
                break
        else:
            print("ERROR: User not found:", session.username)
            await sleep_ms(1000)  # throttle repeated bad attempts
            await self.send_response(
                430, "Invalid username or password.", session.ctrl_writer
            )
            return False

        # Next, decode the fields.
        if cred.count(":") == 6:  # Unix-style /etc/passwd entry
            (
                cred_user,
                cred_pw,
                cred_uid,
                cred_gid,
                cred_gecos,
                cred_home,
                cred_shell,
            ) = cred.split(":")
            cred_uid = int(cred_uid)
            cred_gid = int(cred_gid)
        else:
            print("ERROR: Stored credential is invalid for:", session.username)
            await sleep_ms(1000)
            await self.send_response(
                430, "Invalid username or password.", session.ctrl_writer
            )
            return False

        # Finally, validate the user's password.
        if cred_pw.count("$") == 3:  # Hashed format is: $alg$salt$saltedHashedPassword
            self.debug(
                f"Validating user {session.username} against hashed password: {cred_pw}"
            )
            authenticated = SHA256AES.verify_passwd_entry(cred_pw, pass_response)
        else:
            self.debug(
                f"Validating user {session.username} against cleartext password: ********"
            )
            authenticated = pass_response == cred_pw  # Cleartext comparison.

        if authenticated:
            print(f"INFO: Successful login for: {session.username}@{session.client_ip}")
            await self.send_response(230, "Login successful.", session.ctrl_writer)
            session.uid = cred_uid
            session.gid = cred_gid
            session._home_dir = cred_home
            self.debug(f"user={session.username}, uid={session.uid}, gid={session.gid}")
            if not session.home:
                session.cwd = "/"
            else:
                self.debug(f"Changing working directory to user home: {session.home}")
                try:
                    stat(session.home)
                except OSError:
                    self.debug("User home directory not present. Defaulting to: /")
                    session.cwd = "/"
                else:
                    session.cwd = session.home
            return True
        else:
            await sleep_ms(1000)
            await self.send_response(
                430, "Invalid username or password.", session.ctrl_writer
            )
            return False

    async def pasv(self, _, session):
        """
        Start a new data listener on one of the high numbered ports and
        report back to the client. RFC-959

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        host_octets = self.host.replace(".", ",")
        port = self.get_pasv_port()
        port_octet_high = port // 256
        port_octet_low = port % 256
        self.debug(f"Starting data listener on port: {self.host}:{port}")
        session.data_listener = await start_server(
            self.on_data_connect, self.host, port, 1
        )
        await self.send_response(
            227,
            f"Entering passive mode. ({host_octets},{port_octet_high},{port_octet_low})",
            session.ctrl_writer,
        )
        return True

    async def port(self, address, session):
        """
        Open a connection to the FTP client at the specified address/port.

        Args:
            address (string): comma-separated octets as specified in RFC-959
            session (object): the FTP client's login session info
        Returns:
            boolean: always True
        """
        self.debug(f"Port address: {address}")
        if address.count(",") != 5:
            await self.send_response(451, "Invalid parameter.", session.ctrl_writer)
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
                    425, "Could not open data connection.", session.ctrl_writer
                )
            else:
                await self.send_response(200, "OK.", session.ctrl_writer)
        return True

    async def pwd(self, _, session):
        """
        Report back with the current working directory.
        RFC-959 specifies as PWD, RFC-775 specifies as XPWD

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        await self.send_response(257, f'"{session.cwd}"', session.ctrl_writer)
        return True

    async def quit(self, _, session):
        """
        User sign off. Returning False signals exit by the control channel loop.
        RFC-959

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always False
        """
        await self.send_response(221, f"Bye, {session.username}.", session.ctrl_writer)
        return False

    async def retr(self, filepath, session):
        """
        Given a file path, retrieve the file from flash ram and send it to
        the client over the data connection established by PASV. RFC-959

        Args:
            file (string): a path indicating the file resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        if not filepath:
            await self.send_response(501, "Missing parameter.", session.ctrl_writer)
        else:
            filepath = FTPdLite.decode_path(filepath, session)
            try:
                stat(filepath)
            except OSError:
                await self.send_response(550, "No such file.", session.ctrl_writer)
            else:
                if await self.verify_data_connection(session) is False:
                    await self.send_response(
                        426,
                        "Data connection closed. Transfer aborted.",
                        session.ctrl_writer,
                    )
                else:
                    await self.send_response(
                        150, "Transferring file.", session.ctrl_writer
                    )
                    try:
                        with open(filepath, "rb") as file:
                            for chunk in FTPdLite.read_file_chunk(file):
                                session.data_writer.write(chunk)
                                await session.data_writer.drain()
                    except OSError:
                        await self.send_response(
                            451, "Error reading file.", session.ctrl_writer
                        )
                    else:
                        await self.send_response(
                            226, "Transfer finished.", session.ctrl_writer
                        )
                        await self.close_data_connection(session)
        return True

    async def rmd(self, dirpath, session):
        """
        Given a directory path, remove the directory. Must be empty.
        RFC-959 specifies as RKD, RFC-775 specifies as XRKD
        """
        if not dirpath:
            await self.send_response(501, "Missing parameter.", session.ctrl_writer)
        else:
            if session.has_write_access(dirpath) is False:
                await self.send_response(550, "No access.", session.ctrl_writer)
            else:
                dirpath = FTPdLite.decode_path(dirpath, session)
                try:
                    rmdir(dirpath)
                except OSError:
                    await self.send_response(
                        550,
                        "No such directory or directory not empty.",
                        session.ctrl_writer,
                    )
                else:
                    await self.send_response(250, "OK.", session.ctrl_writer)
        return True

    async def site(self, param, session):
        """
        RFC-959 specifies SITE as a way to access services not defined
        in the common set of FTP commands. This server offers several
        Unix-style commands as well as a few MicroPython-specific ones.
        """
        if " " in param:
            site_cmd = param.split(None, 1)[0].lower()
            site_param = param.split(None, 1)[1]
        else:
            site_cmd = param.lower()
            site_param = ""
        try:
            func = self._site_cmd_dict[site_cmd]
        except KeyError:
            await self.send_response(
                504, "Parameter not supported.", session.ctrl_writer
            )
        else:
            status, output = await func(site_param, session)
            await self.send_response(status, output, session.ctrl_writer)
        return True

    async def site_date(self, param, session):
        if param == "help":
            return 214, "show the system's current date and time"
        else:
            now = FTPdLite.date_format(time())
            output = f"{now}"
            return 211, output

    async def site_df(self, param, session):
        if param == "help":
            return 214, "report file system space usage"
        else:
            param = param or "/"
            try:
                properties = statvfs(param)
            except OSError:
                return 501, "Invalid filesystem."
            else:
                fragment_size = properties[1]
                blocks_total = properties[2]
                blocks_available = properties[4]
                size = int(blocks_total * fragment_size)
                size_hr = FTPdLite.human_readable(size)
                avail = int(blocks_available * fragment_size)
                avail_hr = FTPdLite.human_readable(avail)
                used = size - avail
                used_hr = FTPdLite.human_readable(used)
                percent_used = round(100 * used / size)
                output = [
                    "Filesystem        Size        Used       Avail      Use%",
                    f"{param:12s}  {size_hr:>8s}    {used_hr:>8s}    {avail_hr:>8s}      {percent_used:3d}%",
                    "End.",
                ]
            return 211, output

    async def site_free(self, param, session):
        if param == "help":
            return 214, "display free and used memory"
        else:
            free = mem_free() // 1024
            used = mem_alloc() // 1024
            total = (mem_free() + mem_alloc()) // 1024
            output = [
                "         Total       Used      Avail",
                f"Mem: {total:6d}KiB  {used:6d}KiB  {free:6d}KiB",
                "End.",
            ]
            return 211, output

    async def site_gc(self, param, session):
        if param == "help":
            return 214, "run garbage collection"
        else:
            before = mem_free()
            gc_collect()
            after = mem_free()
            regained_kb = (after - before) // 1024
            output = f"Additional {regained_kb}KiB available."
            return 211, output

    async def site_help(self, topic, session):
        if topic == "help":
            return 214, "get brief description of a command"
        else:
            output = ["Available SITE commands:"]
            max_width = 0
            for cmd in self._site_cmd_dict:
                max_width = max(max_width, len(cmd))
            commands = sorted(list(self._site_cmd_dict.keys()))
            for c in range(len(commands)):
                func = self._site_cmd_dict[commands[c]]
                _, cmd_help = await func("help", session)  # discard status code
                output.append(f"  {commands[c]:>{max_width}s}  {cmd_help}")
            output.append("End.")
            return 214, output

    async def site_kick(self, param, session):
        if param == "help":
            return 214, "disconnect a session by username or IP"
        elif param == "":
            return 501, "Missing parameter."
        elif session.gid != 0:
            return 550, "Not authorized."
        else:
            matching_sessions = await self.find_session(param)
            self.debug(f"Found {len(matching_sessions)} sessions for {param}")
            if len(matching_sessions) < 1:
                return 450, "Not found."
            elif len(matching_sessions) > 1:
                return 450, f"Multiple instances of {param} exist."
            else:
                print(
                    f"INFO: User {session.username} kicked session: {matching_sessions[0].username}@{matching_sessions[0].client_ip}"
                )
                await self.delete_session(matching_sessions[0])
                return 211, f"Kicked {param}"

    async def site_shutdown(self, param, session):
        if param == "help":
            return 214, "refuse new connections, halt (-h), or reboot (-r)"
        else:
            self.debug(
                f"Shutdown request by: {session.username}@{session.client_ip} with UID:GID = {session.uid}:{session.gid}"
            )
            if session.uid != 0 and session.gid != 10:
                return 550, "Not authorized."
            else:
                print("INFO: Syncing filesystems.")
                sync()
                await sleep_ms(1000)
                sync()
                if param is None or param == "":
                    self._accepting_connections = False
                    return 211, "Server will refuse new connections."
                if param == "-h":
                    await self.send_response(
                        221, "Server going down for deep sleep.", session.ctrl_writer
                    )
                    await sleep_ms(1000)
                    deepsleep()
                elif param == "-r":
                    await self.send_response(
                        221, "Server going down for reboot.", session.ctrl_writer
                    )
                    await sleep_ms(1000)
                    reset()
                else:
                    return 501, "Invalid parameter."

    async def site_uptime(self, param, session):
        if param == "help":
            return 214, "tell how long the system's been running"
        else:
            seconds = time() - self._start_time
            days = seconds // 86400
            seconds = seconds % 86400
            hours = seconds // 3600
            seconds = seconds % 3600
            mins = seconds // 60
            mins_pad = "0" if mins < 10 else ""
            now = FTPdLite.date_format(time())
            output = f"{now} up {days} days, {hours}:{mins_pad}{mins}, {len(self._session_list)} users"
            return 211, output

    async def site_who(self, param, session):
        if param == "help":
            return 214, "show who's logged in"
        else:
            user_width = 0
            addr_width = 0
            output = ["Current users:"]
            for s in self._session_list:
                user_width = max(user_width, len(s.username))
                addr_width = max(addr_width, len(s.client_ip))
            for s in self._session_list:
                login_time = FTPdLite.date_format(s.login_time)
                output.append(
                    f"{s.username:{user_width}s}  {s.client_ip:{addr_width}s}  {login_time}"
                )
            output.append(f"Total: {len(self._session_list)}")
            return 211, output

    async def site_whoami(self, param, session):
        if param == "help":
            return 214, "display info for current user"
        else:
            login_time = FTPdLite.date_format(session.login_time)
            output = f"{session.username}  {session.client_ip}  {login_time}"
            return 211, output

    async def size(self, filepath, session):
        """
        Given a file path, reply with the number of bytes in the file.
        Defined in RFC-3659.
        """
        if not filepath:
            await self.send_response(501, "Missing parameter.", session.ctrl_writer)
        else:
            filepath = FTPdLite.decode_path(filepath, session)
            try:
                size = stat(filepath)[6]
            except OSError:
                await self.send_response(550, "No such file.", session.ctrl_writer)
            else:
                await self.send_response(213, f"{size}", session.ctrl_writer)
        return True

    async def stat(self, pathname, session):
        """
        Report sytem status or existence of file/dir. RFC-959

        Args:
            pathname (string): path to a file or directory

        Returns:
            boolean: always True
        """
        if pathname is None or pathname == "":
            server_status = [
                f"{self._server_name}",
                f"Connected to: {hostname()}",
                f"Logged in as: {session.username}",
                "TYPE: L8, FORM: Nonprint; STRUcture: File; transfer MODE: Stream",
                "End.",
            ]
            await self.send_response(211, server_status, session.ctrl_writer)
        else:
            try:
                properties = stat(pathname)
            except OSError:
                await self.send_response(
                    550, "No such file or directory.", session.ctrl_writer
                )
            else:
                if properties[0] & 0x4000:  # entry is a directory
                    await self.send_response(213, f"{pathname}", session.ctrl_writer)
                else:
                    await self.send_response(211, f"{pathname}", session.ctrl_writer)
        return True

    async def stor(self, filepath, session):
        """
        Given a file path, open a data connection and write the incoming
        stream data to the file. RFC-959
        """
        if not filepath:
            await self.send_response(501, "Missing parameter.", session.ctrl_writer)
        else:
            if session.has_write_access(filepath) is False:
                await self.send_response(550, "No access.", session.ctrl_writer)
            else:
                filepath = FTPdLite.decode_path(filepath, session)
                if await self.verify_data_connection(session) is False:
                    await self.send_response(
                        426,
                        "Data connection closed. Transfer aborted.",
                        session.ctrl_writer,
                    )
                else:
                    await self.send_response(
                        150, "Transferring file.", session.ctrl_writer
                    )
                    try:
                        with open(filepath, "wb") as file:
                            while True:
                                chunk = await session.data_reader.read(512)
                                if chunk:
                                    file.write(chunk)
                                else:
                                    break
                    except OSError:
                        await self.send_response(
                            451, "Error writing file.", session.ctrl_writer
                        )
                    else:
                        await self.send_response(
                            226, "Transfer finished.", session.ctrl_writer
                        )
                        await self.close_data_connection(session)
        return True

    async def stru(self, param, session):
        """
        Obsolete, but included for compatibility. RFC-959

        Args:
            param (string): single character to indicate file structure

        Returns:
            boolean: always True
        """
        if param.upper() == "F":
            await self.send_response(200, "OK.", session.ctrl_writer)
        else:
            await self.send_response(
                504, "File structure not supported.", session.ctrl_writer
            )
        return True

    async def syst(self, _, session):
        """
        Reply to indicate this server follows Unix conventions. RFC-959
        """
        await self.send_response(215, "UNIX Type: L8", session.ctrl_writer)
        return True

    async def type(self, type, session):
        """
        TYPE is implemented to satisfy some clients, but doesn't actually
        do anything to change the translation of end-of-line characters
        for this server. RFC-959
        """
        if type.upper() in ("A", "A N", "I", "L 8"):
            await self.send_response(200, "Always in binary mode.", session.ctrl_writer)
        else:
            await self.send_response(504, "Invalid type.", session.ctrl_writer)
        return True

    async def user(self, username, session):
        """
        Record the username and prompt for a password. RFC-959

        Args:
            username (string): the USER presented at the login prompt
            session (object): info about the client session, including streams

        Returns:
            boolean: always True

        """
        if not self._accepting_connections and username != "root":
            await self.send_response(
                421, "Not accepting connections.", session.ctrl_writer
            )
            return False
        else:
            session.username = username
            await self.send_response(
                331, f"Password required for {username}.", session.ctrl_writer
            )
            return True

    async def kick_stale(self, timeout):
        """
        Clean up inactive user sessions.

        Args:
            timeout (int): minutes of inactivity to allow before closing
        """
        self.debug(
            f"Stale session sweep scheduled with a {timeout} minute idle timeout."
        )
        while True:
            await sleep_ms(60000)
            for s in self._session_list:
                idle_minutes = (time() - s.last_active_time) // 60
                self.debug(
                    f"Idle time for {s.username}@{s.client_ip} is {idle_minutes} minutes."
                )
                if idle_minutes > timeout:
                    print(f"INFO: Kicking stale session: {s.username}@{s.client_ip}")
                    await self.delete_session(s)

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

    async def close_data_connection(self, session):
        """
        Close data connection streams and remove them from the session.

        Args:
            session (object): info about the client session, including streams

        Returns: nothing
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
            print("ERROR: Multiple sessions found for {client_ip}")
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

        Returns: nothing
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

        Returns: nothing
        """
        client_ip, client_port = ctrl_writer.get_extra_info("peername")
        print(f"INFO: Connection from client: {client_ip}")
        if (
            len(self._session_list) > 10  # completely arbitrary limit
            or await self.find_session(client_ip) != []
        ):
            await self.send_response(421, "Too many connections.", ctrl_writer)
        else:
            session = Session(client_ip, client_port, ctrl_reader, ctrl_writer)
            self._session_list.append(session)
            session_active = True  # Becomes False on QUIT or other disconnection event.
            await self.send_response(220, self._server_name, ctrl_writer)
            while session_active:
                try:
                    request = await ctrl_reader.read(self._request_buffer_size)
                except OSError:  # Unexpected disconnection.
                    print(
                        f"ERROR: Control connection closed for: {session.username}@{session.client_ip}"
                    )
                    session_active = False
                    await self.close_data_connection(session)
                    break
                else:
                    session.last_active_time = time()
                    verb, param = self.parse_request(request)
                try:
                    func = self._ftp_cmd_dict[verb]
                except KeyError:
                    await self.send_response(
                        502, "Command not implemented.", ctrl_writer
                    )
                else:
                    session_active = await func(param, session)
            self.close_ctrl_connection(session)
            print(f"INFO: Session disconnected: {session.username}@{session.client_ip}")
            await self.delete_session(session)
            del session

    def run(self, host="127.0.0.1", port=21, idle_timeout=60, loop=None, debug=False):
        """
        Start an asynchronous listener for FTP requests.

        Args:
            host (string): the IP address of the interface on which to listen
            port (int): the TCP port on which to listen
            idle_timeout (int): minutes of inactivity before a session is kicked
            loop (object): asyncio loop that the server should insert itself into
            debug (boolean): True indicates verbose logging is desired

        Returns:
            object: the same loop object given as a parameter or a new one if
              no existing loop was passed
        """
        self._debug = debug
        now = time()
        jan_1_2023 = mktime((2023, 1, 1, 0, 0, 0, 0, 1))
        if now < jan_1_2023:
            print("WARNING: System clock not set. File timestamps will be incorrect.")
        addrinfo = getaddrinfo(host, port)[0]
        assert addrinfo[0] == AF_INET, "ERROR: This server only supports IPv4."
        self.host = addrinfo[-1][0]
        self.port = addrinfo[-1][1]
        print(f"Listening on {self.host}:{self.port}")
        loop = get_event_loop()
        server = start_server(self.on_ctrl_connect, self.host, self.port, 5)
        loop.create_task(server)
        loop.create_task(self.kick_stale(idle_timeout))
        self._accepting_connections = True
        loop.run_forever()
