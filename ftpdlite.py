"""
File systems in flight. FTPdLite!
(With apologies to Starland Vocal Band)

FTPdLite is a minimalist, mostly RFC 959 compliant, MicroPython FTP
server for 99% of your microcontroller file transferring needs.

(c)2023 David Horton.
Released under the BSD-2-Clause license.
Project site: https://github.com/DavesCodeMusings/ftpdlite

"""

# Many thanks to https://cr.yp.to/ftp.html for a clear explanation of FTP.

from asyncio import get_event_loop, open_connection, sleep_ms, start_server
from os import chdir, getcwd, listdir, mkdir, remove, rmdir, stat, statvfs
from time import localtime, mktime, time
from network import hostname
from socket import getaddrinfo, AF_INET


class Session:
    """
    An interactive connection from a client.
    """

    def __init__(self, client_ip, client_port, ctrl_reader, ctrl_writer):
        self._client_ip = client_ip
        self._client_port = client_port
        self._ctrl_reader = ctrl_reader
        self._ctrl_writer = ctrl_writer
        self._data_reader = None
        self._data_writer = None
        self._username = None
        self._login_time = time()

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

    @property
    def data_writer(self):
        return self._data_writer

    @data_writer.setter
    def data_writer(self, stream):
        self._data_writer = stream

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, username):
        self._username = username

    @property
    def login_time(self):
        return self._login_time


class FTPdLite:
    """
    A minimalist FTP server for MicroPython.
    """

    def __init__(
        self,
        readonly=False,
        pasv_port_range=range(49152, 49407),
        request_buffer_size=512,
    ):
        self.server_name = "FTPdLite (MicroPython)"
        self.credentials = "Felicia:Friday"
        self.readonly = readonly
        self.start_time = time()
        self.request_buffer_size = request_buffer_size
        self.pasv_port_pool = list(pasv_port_range)
        self.session_list = []
        self.command_dictionary = {
            "CWD": self.cwd,
            "FEAT": self.feat,
            "HELP": self.help,
            "LIST": self.list,
            "MODE": self.mode,
            "NLST": self.nlst,
            "NOOP": self.noop,
            "OPTS": self.opts,
            "PASS": self.passwd,
            "PASV": self.pasv,
            "PORT": self.port,
            "PWD": self.pwd,
            "QUIT": self.quit,
            "RETR": self.retr,
            "SITE": self.site,
            "SIZE": self.size,
            "STAT": self.stat,
            "STRU": self.stru,
            "SYST": self.syst,
            "TYPE": self.type,
            "USER": self.user,
            "XCWD": self.cwd,
            "XPWD": self.pwd,
        }
        if readonly is True:
            self.command_dictionary.update(
                {
                    "DELE": self.no_permission,
                    "MKD": self.no_permission,
                    "RMD": self.no_permission,
                    "STOR": self.no_permission,
                    "XMKD": self.no_permission,
                    "XRMD": self.no_permission,
                }
            )
        else:
            self.command_dictionary.update(
                {
                    "DELE": self.dele,
                    "MKD": self.mkd,
                    "RMD": self.rmd,
                    "STOR": self.stor,
                    "XMKD": self.mkd,
                    "XRMD": self.rmd,
                }
            )

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
        mon = months[datetime[1] - 1]
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
    def decode_path(path, empty_means_cwd=False):
        """
        Given a file or directory path, validate it and return an absolute path.

        Args:
            path (string): a relative, absolute, or empty path to a resource
            empty_means_cwd (boolean): flag to use CWD in place of empty path

        Returns:
            string: an absolute path to the resource
        """
        if path is None or path == "" and empty_means_cwd is True:
            absolute_path = getcwd()
        elif path.startswith("/") is False:
            absolute_path = FTPdLite.path_join(getcwd(), path)
        else:
            absolute_path = path
        return absolute_path

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

    async def delete_session(self, session):
        """
        Given a session object, delete is from the server's session list.

        Args:
            session (object): the client IP of interest

        Returns: nothing
        """
        for i in range(len(self.session_list)):
            if self.session_list[i] == session:
                del(self.session_list[i])
                break

    async def find_session(self, search_ip):
        """
        Given a client IP address, find the associated session.

        Args:
            search_ip (string): the client IP of interest

        Returns:
            object: the Session object with the associated client_ip
        """
        for s in self.session_list:
            if s.client_ip == search_ip:
                break
        else:
            s = None
        return s

    async def get_pasv_port(self):
        """
        Get a TCP port number from the pool, then rotate the list to ensure
        it won't be used again for a while. Helps avoid address in use error.

        Returns:
            integer: TCP port number
        """
        port = self.pasv_port_pool.pop(0)
        self.pasv_port_pool.append(port)
        return port

    async def parse_request(self, req_buffer):
        """
        Given a line of input, split the command into a verb and parameter.

        Args:
            req_buffer (bytes): the unprocessed request from the client

        Returns:
            verb, param (tuple): action and related parameter string
        """
        request = req_buffer.decode("utf-8").rstrip("\r\n")
        if len(request) == 0:
            verb = None
            param = None
            print("[null]")
        elif " " not in request:
            verb = request.upper()
            param = None
            print(verb)
        else:
            verb = request.split(None, 1)[0].upper()
            try:
                param = request.split(None, 1)[1]
            except IndexError:
                param = ""
            if verb == "PASS":
                print(verb, "********")
            else:
                print(verb, param)
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
            nothing
        """
        if code == 250 and msg is None:
            msg = "OK."
        elif isinstance(msg, str):  # single line
            print(f"{code} {msg}")
            writer.write(f"{code} {msg}\r\n")
        elif isinstance(msg, list):  # multi-line, dashes after code
            for line in range(len(msg) - 1):
                print(f"{code}-{msg[line]}")
                writer.write(f"{code}-{msg[line]}\r\n")
            print(f"{code} {msg[-1]}")
            writer.write(f"{code} {msg[-1]}\r\n")  # last line, no dash
        await writer.drain()

    # Each command function below returns a boolean to indicate if session
    # should be maintained (True) or ended (False.) Most return True.

    async def cwd(self, dirpath, session):
        """
        Change working directory.

        Args:
            dirpath (string): a path indicating a directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        dirpath = FTPdLite.decode_path(dirpath)
        try:
            chdir(dirpath)
        except OSError:
            await self.send_response(550, "No such directory.", session.ctrl_writer)
        else:
            await self.send_response(250, getcwd(), session.ctrl_writer)
        return True

    async def dele(self, filepath, session):
        """
        Given a path, delete the file.

        Args:
            filepath (string): a path indicating a file resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        filepath = FTPdLite.decode_path(filepath)
        try:
            remove(filepath)
        except OSError:
            await self.send_response(550, "No such file.", session.ctrl_writer)
        else:
            await self.send_response(250, "OK.", session.ctrl_writer)
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
        features = ["Extensions supported:", "SIZE", "End."]
        await self.send_response(211, features, session.ctrl_writer)
        return True

    async def help(self, _, session):
        """
        Reply with help only in a general sense, not per individual command.

        Args:
            _ (discard): this server does not support specific topics
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        await self.send_response(
            211,
            "[FTPdLite](https://github.com/DavesCodeMusings/ftpdlite)",
            session.ctrl_writer,
        )
        return True

    async def list(self, dirpath, session):
        """
        Send a Linux style directory listing, though ownership and permission
        has no meaning in the flash filesystem.

        Args:
            dirpath (string): a path indicating a directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        dirpath = FTPdLite.decode_path(dirpath, empty_means_cwd=True)
        try:
            dir_entries = listdir(dirpath)
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
                await self.send_response(150, dirpath, session.ctrl_writer)
                for entry in dir_entries:
                    properties = stat(dirpath + "/" + entry)
                    if properties[0] & 0x4000:  # entry is a directory
                        permissions = "dr-xr-xr-x" if self.readonly else "drwxr-xr-x"
                        size = 0
                        entry += "/"
                    else:
                        permissions = "-r--r--r--" if self.readonly else "-rw-r--r--"
                        size = properties[6]
                    uid = "root" if properties[4] == 0 else properties[4]
                    gid = "root" if properties[5] == 0 else properties[5]
                    mtime = FTPdLite.date_format(properties[8])
                    formatted_entry = f"{permissions}  1  {uid:4}  {gid:4}  {size:10d}  {mtime:>11s}  {entry}"
                    print(formatted_entry)
                    session.data_writer.write(formatted_entry + "\r\n")
                await session.data_writer.drain()
                await self.send_response(
                    226, "Directory list sent.", session.ctrl_writer
                )
                await self.close_data_connection(session)
        return True

    async def mode(self, param, session):
        """
        Obsolete, but included for compatibility.

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

        Args:
            dirpath (string): a path indicating the directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        dirpath = FTPdLite.decode_path(dirpath)
        try:
            mkdir(dirpath)
            await self.send_response(250, f'"{dirpath}"', session.ctrl_writer)
        except OSError:
            await self.send_response(
                550, "Failed to create directory.", session.ctrl_writer
            )
        return True

    async def nlst(self, dirpath, session):
        """
        Send a list of file names only, without the extra information.

        Args:
            dirpath (string): a path indicating a directory resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        dirpath = FTPdLite.decode_path(dirpath, empty_means_cwd=True)
        try:
            dir_entries = listdir(dirpath)
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
                await self.send_response(150, dirpath, session.ctrl_writer)
                print("\n".join(dir_entries))
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

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        await self.send_response(200, "Take your time. I'll wait.", session.ctrl_writer)
        return True

    async def no_permission(self, _, session):
        """
        Return an error. Used when the server is in readonly mode.

        Args:
            _ (discard): throw away parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        await self.send_response(550, "No access.", session.ctrl_writer)
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

    async def passwd(self, password, session):
        """
        Verify user credentials and drop the connection if incorrect.

        Args:
            password (string): the cleartext password
            session (object): the FTP client's login session info

        Returns:
            boolean: True if login succeeded, False if not
        """
        if self.debug:
            print("Expecting:", self.credentials)
            print(f"Got: {session.username}:{password}")
        if (
            session.username == self.credentials.split(":", 1)[0]
            and password == self.credentials.split(":", 1)[1]
        ):
            await self.send_response(230, "Login successful.", session.ctrl_writer)
            return True
        else:
            await sleep_ms(1000)  # throttle repeated bad attempts
            await self.send_response(
                430, "Invalid username or password.", session.ctrl_writer
            )
            return False

    async def pasv(self, _, session):
        """
        Start a new data listener on one of the high numbered ports and
        report back to the client.

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        host_octets = self.host.replace(".", ",")
        port = await self.get_pasv_port()
        port_octet_high = port // 256
        port_octet_low = port % 256
        if self.debug:
            print(f"Starting data listener on port: {self.host}:{port}")
        session.data_listener = await start_server(
            self.on_data_connect, self.host, port, 1
        )
        await self.send_response(
            227,
            f"Entering passive mode ={host_octets},{port_octet_high},{port_octet_low}",
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
        print(f"Port address: {address}")
        if address.count(",") != 5:
            await self.send_response(451, "Invalid parameter.", session.ctrl_writer)
        else:
            a = address.split(",")
            host = f"{a[0]}.{a[1]}.{a[2]}.{a[3]}"
            port = int(a[4]) * 256 + int(a[5])
            print(f"Opening data connection to: {host}:{port}")
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

        Args:
            _ (discard): command does not take parameters
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        await self.send_response(257, f'"{getcwd()}"', session.ctrl_writer)
        return True

    async def quit(self, _, session):
        """
        User sign off. Returning False signals exit by the control channel loop.

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
        the client over the data connection established by PASV.

        Args:
            file (string): a path indicating the file resource
            session (object): the FTP client's login session info

        Returns:
            boolean: always True
        """
        filepath = FTPdLite.decode_path(filepath)
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
                await self.send_response(150, "Transferring file.", session.ctrl_writer)
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
        """
        dirpath = FTPdLite.decode_path(dirpath)
        try:
            rmdir(dirpath)
        except OSError:
            await self.send_response(
                550, "No such directory or directory not empty.", session.ctrl_writer
            )
        else:
            await self.send_response(250, "OK.", session.ctrl_writer)
        return True

    async def site(self, param, session):
        """
        RFC959 specifies SITE as a way to access services not defined
        in the common set of FTP commands. This server offers the Unix-
        style `df` command as a way to show file system utilization.
        """
        if param.lower() == "df":
            properties = statvfs("/")
            fragment_size = properties[1]
            blocks_total = properties[2]
            blocks_available = properties[4]
            size_kb = int(blocks_total * fragment_size / 1024)
            avail_kb = int(blocks_available * fragment_size / 1024)
            used_kb = size_kb - avail_kb
            percent_used = round(100 * used_kb / size_kb)
            df_output = [
                "Filesystem      Size      Used     Avail   Use%",
                f"flash      {size_kb:8d}K {used_kb:8d}K {avail_kb:8d}K   {percent_used:3d}%",
                "End.",
            ]
            await self.send_response(211, df_output, session.ctrl_writer)
        else:
            await self.send_response(
                504, "Parameter not supported.", session.ctrl_writer
            )
        return True

    async def size(self, filepath, session):
        """
        Given a file path, reply with the number of bytes in the file.
        Defined in RFC-3659.
        """
        filepath = FTPdLite.decode_path(filepath)
        try:
            size = stat(filepath)[6]
        except OSError:
            await self.send_response(550, "No such file.", session.ctrl_writer)
        else:
            await self.send_response(213, f"{size}", session.ctrl_writer)
        return True

    async def stat(self, pathname, session):
        """
        Report sytem status or existence of file/dir.

        Args:
            pathname (string): path to a file or directory

        Returns:
            boolean: always True
        """
        if pathname is None or pathname == "":
            seconds = time() - self.start_time
            days = seconds // 86400
            seconds = seconds % 86400
            hours = seconds // 3600
            hour_pad = "0" if hours < 10 else ""
            seconds = seconds % 3600
            mins = seconds // 60
            mins_pad = "0" if mins < 10 else ""
            server_status = [
                f"{self.server_name}",
                f"System date: {FTPdLite.date_format(time())}",
                f"Uptime: {days} days, {hour_pad}{hours}:{mins_pad}{mins}",
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
        stream data to the file.
        """
        filepath = FTPdLite.decode_path(filepath)
        if await self.verify_data_connection(session) is False:
            await self.send_response(
                426, "Data connection closed. Transfer aborted.", session.ctrl_writer
            )
        else:
            await self.send_response(150, "Transferring file.", session.ctrl_writer)
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
                await self.send_response(226, "Transfer finished.", session.ctrl_writer)
                await self.close_data_connection(session)
        return True

    async def stru(self, param, session):
        """
        Obsolete, but included for compatibility.

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
        Reply to indicate this server follows Unix conventions.
        """
        await self.send_response(215, "UNIX Type: L8", session.ctrl_writer)
        return True

    async def type(self, type, session):
        """
        TYPE is implemented to satisfy some clients, but doesn't actually
        do anything to change the translation of end-of-line characters.
        """
        if type.upper() in ("A", "A N", "I", "L 8"):
            await self.send_response(200, "Always in binary mode.", session.ctrl_writer)
        else:
            await self.send_response(504, "Invalid type.", session.ctrl_writer)
        return True

    async def user(self, username, session):
        """
        Record the username and prompt for a password.

        Args:
            username (string): the USER presented at the login prompt
            session (object): info about the client session, including streams

        Returns:
            boolean: always True

        """
        session.username = username
        await self.send_response(
            331, f"Password required for {username}.", session.ctrl_writer
        )
        return True

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
        if self.debug:
            print("Closing data connection...")
        try:
            session.data_writer
        except AttributeError:
            if self.debug:
                print("No data writer stream exists to be closed.")
        else:
            session.data_writer.close()
            await session.data_writer.wait_closed()
            session.data_writer = None
        try:
            session.data_reader
        except AttributeError:
            if self.debug:
                print("No data reader stream exists to be closed.")
        else:
            session.data_reader.close()
            await session.data_reader.wait_closed()
            session.data_reader = None
        try:
            session.data_listener
        except AttributeError:
            if self.debug:
                print("No data listener object exists to be closed.")
        else:
            session.data_listener.close()
            await session.data_listener.wait_closed()
            session.data_listener = None
        if self.debug:
            print("Data connection closed.")

    async def on_data_connect(self, data_reader, data_writer):
        """
        Handler for PASV data connections. Remember the streams for later commands.

        Args:
            data_reader (stream): files uploaded from the client
            data_writer (stream): files/data requested by the client
        """
        client_ip, client_port = data_writer.get_extra_info("peername")
        if self.debug:
            print(f"Data connection from: {client_ip}:{client_port}")

        session = await self.find_session(client_ip)
        if self.debug:
            print(session)
        session.data_reader = data_reader
        session.data_writer = data_writer

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
        if self.debug:
            print(f"Control connection closed for {session.client_ip}")

    async def on_ctrl_connect(self, ctrl_reader, ctrl_writer):
        """
        Handler for control connection. Parses commands to carry out actions.

        Args:
            ctrl_reader (stream): incoming commands from the client
            ctrl_writer (stream): replies from the server to the client

        Returns: nothing
        """
        client_ip, client_port = ctrl_writer.get_extra_info("peername")
        print(f"Connection from client: {client_ip}")
        if (
            len(self.session_list) > 10
            or await self.find_session(client_ip) is not None
        ):
            await self.send_response(421, "Too many connections.", ctrl_writer)
        else:
            session = Session(client_ip, client_port, ctrl_reader, ctrl_writer)
            self.session_list.append(session)
            session_active = True  # Becomes False on QUIT or other disconnection event.
            await self.send_response(220, self.server_name, ctrl_writer)
            while session_active:
                try:
                    request = await ctrl_reader.read(self.request_buffer_size)
                except OSError:  # Unexpected disconnection.
                    session_active = False
                    await self.close_data_connection(session)
                    break
                else:
                    verb, param = await self.parse_request(request)
                try:
                    func = self.command_dictionary[verb]
                except KeyError:
                    await self.send_response(
                        502, "Command not implemented.", ctrl_writer
                    )
                else:
                    session_active = await func(param, session)
            self.close_ctrl_connection(session)
            await self.delete_session(session)
            session = None

    def run(self, host="127.0.0.1", port=21, loop=None, debug=False):
        """
        Start an asynchronous listener for FTP requests.

        Args:
            host (string): the IP address of the interface on which to
              listen (0.0.0.0 means all interfaces)
            port (int): the TCP port on which to listen
            loop (object): the asyncio loop that the server should
              insert itself into
            debug (boolean): True indicates verbose logging is desired

        Returns:
            object: the same loop object given as a parameter or a new
              one if no existing loop was passed
        """
        self.debug = debug
        now = time()
        jan_1_2023 = mktime((2023, 1, 1, 0, 0, 0, 0, 1))
        if now < jan_1_2023:
            print("WARNING: System clock not set. File timestamps will be incorrect.")
        addrinfo = getaddrinfo(host, port)[0]
        if debug:
            print("getaddrinfo() =", addrinfo)
        assert addrinfo[0] == AF_INET, "ERROR: This server only supports IPv4."
        self.host = addrinfo[-1][0]
        self.port = addrinfo[-1][1]
        print(f"Listening on {self.host}:{self.port}")
        loop = get_event_loop()
        server = start_server(self.on_ctrl_connect, self.host, self.port, 5)
        loop.create_task(server)
        loop.run_forever()
