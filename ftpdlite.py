### File systems in flight. FTPdLite! ###
# Many thanks to https://cr.yp.to/ftp.html for a clear explanation of FTP.

from asyncio import get_event_loop, sleep_ms, start_server
from os import chdir, getcwd, listdir, mkdir, remove, rmdir, stat
from time import localtime, mktime, time


class FTPdLite:
    """
    A minimalist FTP server for MicroPython.
    """

    def __init__(self, readonly=False, request_buffer_size=1024):
        self.server_name = "FTPdLite (MicroPython)"
        self.credentials = "Felicia:Friday"
        self.readonly = readonly
        self.request_buffer_size = request_buffer_size
        self.pasv_port_pool = list(range(49152, 49407))
        self.command_dictionary = {
            "CWD": self.cwd,
            "FEAT": self.feat,
            "HELP": self.help,
            "LIST": self.list,
            "NLST": self.nlst,
            "NOOP": self.noop,
            "OPTS": self.opts,
            "PASS": self.passwd,
            "PASV": self.pasv,
            "PWD": self.pwd,
            "QUIT": self.quit,
            "RETR": self.retr,
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
                    "XMKD": self.mkd,
                    "XRMD": self.rmd,
                }
            )

    @staticmethod
    def date_format(timestamp):
        """
        Turn seconds past the epoch into a human readable date/time to be
        used in Unix-style directory listings.
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
        month = months[datetime[1] - 1]
        day = datetime[2]
        day_space = " " if day < 10 else ""
        year = datetime[0]
        hour = datetime[3]
        hour_padding = "0" if hour < 10 else ""
        minute = datetime[4]
        minute_padding = "0" if minute < 10 else ""
        now = time()
        one_year = 31536000

        if now - timestamp < one_year:
            output = "{} {}{} {}{}:{}{}".format(
                month, day_space, day, hour_padding, hour, minute_padding, minute
            )
        else:
            output = "{} {}{}  {}".format(month, day_space, day, year)
        return output

    @staticmethod
    def decode_path(path, empty_means_cwd=False):
        """
        Given a file or directory path, validate it and return an absolute path.
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
        There's no os.path.join in MicroPython, so...
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
            chunk = file.read(64)  # small chunks to avoid out of memory errors
            if chunk:
                yield chunk
            else:  # empty chunk means end of the file
                return

    def get_pasv_port(self):
        """
        Get a TCP port number from the pool, then rotate the list to ensure
        it won't be used again for a while. Helps avoid address in use error.
        """
        port = self.pasv_port_pool.pop(0)
        self.pasv_port_pool.append(port)
        return port

    def parse_request(self, req_buffer):
        """
        Given a line of input, split the command into a verb and parameter.
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
            param = request.split(None, 1)[1]
            if verb == "PASS":
                print(verb, "********")
            else:
                print(verb, param)
        return verb, param

    async def send_response(self, code, msg, writer):
        """
        Given a status code and a message, send a response to the client.
        """
        if code == 250 and msg is None:
            msg = "OK."
        print(f"{code} {msg}")
        writer.write(f"{code} {msg}\r\n")
        await writer.drain()

    # Each command function below returns a boolean to indicate if session
    # should be maintained (True) or ended (False.) Most return True.

    async def cwd(self, dirpath, writer):
        """
        Change working directory.
        """
        dirpath = FTPdLite.decode_path(dirpath)
        try:
            chdir(dirpath)
        except OSError:
            await self.send_response(550, "No such directory.", writer)
        else:
            await self.send_response(250, getcwd(), writer)
        return True

    async def dele(self, filepath, writer):
        """
        Given a path, delete the file.
        """
        filepath = FTPdLite.decode_path(filepath)
        try:
            remove(filepath)
        except OSError:
            await self.send_response(550, "No such file.", writer)
        else:
            await self.send_response(250, "OK.", writer)
        return True

    async def feat(self, _, writer):
        """
        No features are supported, but reply to satify clients that ask.
        """
        await self.send_response(211, "", writer)  # No features.
        return True

    async def help(self, _, writer):
        """
        Reply with help only in a general sense, not per individual command.
        """
        await self.send_response(
            211, "[FTPdLite](https://github.com/DavesCodeMusings/ftpdlite)", writer
        )
        return True

    async def list(self, dirpath, writer):
        """
        Send a Linux style directory listing, though ownership and permission
        has no meaning in the flash filesystem.
        """
        dirpath = FTPdLite.decode_path(dirpath, empty_means_cwd=True)
        try:
            dir_entries = listdir(dirpath)
        except OSError:
            await self.send_response(451, "Unable to read directory.", writer)
        else:
            await sleep_ms(500)  # kluge to wait for data connection to be ready
            await self.send_response(150, dirpath, writer)
            for entry in dir_entries:
                properties = stat(dirpath + "/" + entry)
                if properties[0] & 0x4000:  # entry is a directory
                    type = "d"
                    size = 0
                else:
                    type = "-"
                    size = properties[6]
                if self.readonly is True:
                    permissions = "r--r--r--"
                else:
                    permissions = "rw-rw-rw-"
                uid = "root" if properties[4] == 0 else properties[4]
                gid = "root" if properties[5] == 0 else properties[5]
                mtime = FTPdLite.date_format(properties[8])
                formatted_entry = f"{type}{permissions}  1  {uid:4}  {gid:4}  {size:10d}  {mtime:>11s}  {entry}"
                print(formatted_entry)
                self.data_writer.write(formatted_entry + "\r\n")
            await self.data_writer.drain()
            await self.send_response(
                226, "Directory list sent. Closing data connection.", writer
            )
            self.data_writer.close()
            await self.data_writer.wait_closed()
            del self.data_writer
            self.data_reader.close()
            await self.data_reader.wait_closed()
            del self.data_reader
            if self.debug:
                print("Data connection closed.")
        return True

    async def mkd(self, dirpath, writer):
        """
        Given a path, create a new directory.
        """
        dirpath = FTPdLite.decode_path(dirpath)
        try:
            mkdir(dirpath)
            await self.send_response(250, f'"{dirpath}"', writer)
        except OSError:
            await self.send_response(550, "Failed to create directory.", writer)
        return True

    async def nlst(self, dirpath, writer):
        """
        Send a list of file names only, without the extra information.
        """
        await sleep_ms(1000)  # kluge to wait for data connection to be ready
        dirpath = FTPdLite.decode_path(dirpath, empty_means_cwd=True)
        try:
            dir_entries = listdir(dirpath)
        except OSError:
            await self.send_response(451, "Unable to read directory.", writer)
        else:
            await self.send_response(150, dirpath, writer)
            print("\n".join(dir_entries))
            self.data_writer.write("\r\n".join(dir_entries) + "\r\n")
            await self.data_writer.drain()
            await self.send_response(
                226, "Directory list sent. Closing data connection.", writer
            )
            self.data_writer.close()
            await self.data_writer.wait_closed()
            del self.data_writer
            self.data_reader.close()
            await self.data_reader.wait_closed()
            del self.data_reader
            if self.debug:
                print("Data connection closed.")
        return True

    async def noop(self, _, writer):
        """
        Do nothing. Used by some clients to stop the connection from timing out.
        """
        await self.send_response(200, "Take your time. I'll wait.", writer)
        return True

    async def no_permission(self, _, writer):
        """
        Return an error. Used when the server is in readonly mode.
        """
        await self.send_response(550, "No access.", writer)
        return True

    async def opts(self, option, writer):
        """
        Reply to the common case of UTF-8, but nothing else.
        """
        if option.upper() == "UTF8 ON":
            await self.send_response(200, "Always in UTF8 mode.", writer)
        else:
            await self.send_response(504, "Unknown option.", writer)
        return True

    async def passwd(self, password, writer):
        """
        Verify user credentials and drop the connection if incorrect.
        """
        if self.debug:
            print("Expecting:", self.credentials)
            print(f"Got: {self.username}:{password}")
        if (
            self.username == self.credentials.split(":", 1)[0]
            and password == self.credentials.split(":", 1)[1]
        ):
            await self.send_response(230, "Login successful.", writer)
            return True
        else:
            await self.send_response(430, "Invalid username or password.", writer)
            return False

    async def pasv(self, _, writer):
        """
        Start a new data listener on one of the high numbered ports and
        report back to the client.
        """
        host_octets = self.host.replace(".", ",")
        port = self.get_pasv_port()
        port_octet_high = port // 256
        port_octet_low = port % 256
        if self.debug:
            print(f"Starting data listener on port: {self.host}:{port}")
        loop = get_event_loop()
        data_listener = start_server(self.on_data_connect, self.host, port, 1)
        await loop.create_task(data_listener)
        await self.send_response(
            227,
            f"Entering passive mode ={host_octets},{port_octet_high},{port_octet_low}",
            writer,
        )
        return True

    async def pwd(self, _, writer):
        """
        Report back with the current working directory.
        """
        await self.send_response(257, f'"{getcwd()}"', writer)
        return True

    async def quit(self, _, writer):
        """
        User sign off. Returning False signals to exit the control channel loop.
        """
        await self.send_response(221, f"Bye, {self.username}.", writer)
        return False

    async def retr(self, filepath, writer):
        """
        Given a file path, retrieve the file from flash ram and send it to
        the client over the data connection established by PASV.
        """
        filepath = FTPdLite.decode_path(filepath)
        try:
            stat(filepath)
        except OSError:
            await self.send_response(550, "No such file.", writer)
        else:
            await sleep_ms(500)  # kluge to wait for data connection to be ready
            try:
                self.data_writer
            except NameError:
                await self.send_response(425, "Data connection failed.", writer)
            else:
                await self.send_response(150, "Transferring file.", writer)
                try:
                    with open(filepath, "rb") as file:
                        for chunk in FTPdLite.read_file_chunk(file):
                            self.data_writer.write(chunk)
                            await self.data_writer.drain()
                except OSError:
                    await self.send_response(451, "Error reading file.", writer)
                else:
                    await self.send_response(226, "Transfer finished.", writer)
            self.data_writer.close()
            await self.data_writer.wait_closed()
            del self.data_writer
            self.data_reader.close()
            await self.data_reader.wait_closed()
            del self.data_reader
            if self.debug:
                print("Data connection closed.")
        return True

    async def rmd(self, dirpath, writer):
        """
        Given a directory path, remove the directory. Must be empty.
        """
        dirpath = FTPdLite.decode_path(dirpath)
        try:
            rmdir(dirpath)
        except OSError:
            await self.send_response(550, "No such directory.", writer)
        else:
            await self.send_response(250, "OK.", writer)
        return True

    async def syst(self, _, writer):
        """
        Reply to indicate this server follows Unix conventions.
        """
        await self.send_response(215, "UNIX Type: L8", writer)
        return True

    async def type(self, type, writer):
        """
        TYPE is implemented to satisfy some clients, but doesn't actually do anything.
        """
        if type.upper() in ("A", "A N", "I", "L 8"):
            await self.send_response(200, f"Type: {type}", writer)
        else:
            await self.send_response(504, "Invalid type.", writer)
        return True

    async def user(self, username, writer):
        """
        Record the username and prompt for a password.
        """
        self.username = username
        await self.send_response(331, f"Password required for {self.username}.", writer)
        return True

    async def on_data_connect(self, data_reader, data_writer):
        """
        Handler for PASV data connections. Remember the streams for later commands.
        """
        client_ip = data_writer.get_extra_info("peername")[0]
        if self.debug:
            print("Data connection from:", client_ip)
        self.data_reader = data_reader
        self.data_writer = data_writer

    async def on_ctrl_connect(self, ctrl_reader, ctrl_writer):
        """
        Handler for control connection. Parses commands to carry out actions.
        """
        client_ip = ctrl_writer.get_extra_info("peername")[0]
        if self.debug:
            print("Control connection from client:", client_ip)
        await self.send_response(220, self.server_name, ctrl_writer)
        session_still_active = True
        while session_still_active:
            request = await ctrl_reader.read(self.request_buffer_size)
            verb, param = self.parse_request(request)
            try:
                func = self.command_dictionary[verb]
            except KeyError:
                await self.send_response(502, "Command not implemented.", ctrl_writer)
            else:
                session_still_active = await func(param, ctrl_writer)

        # End of session
        ctrl_writer.close()
        await ctrl_writer.wait_closed()
        ctrl_reader.close()
        await ctrl_reader.wait_closed()
        if self.debug:
            print(f"Control connection closed for {client_ip}")

    def run(self, host="0.0.0.0", port=21, debug=False):
        """
        Start the FTP server on the given interface and TCP port.
        """
        self.host = host
        self.debug = debug
        now = time()
        jan_1_2023 = mktime((2023, 1, 1, 0, 0, 0, 0, 1))
        if now < jan_1_2023:
            print("WARNING: System clock not set. File timestamps will be incorrect.")
        print(f"Listening on {host}:{port}")
        loop = get_event_loop()
        server = start_server(self.on_ctrl_connect, host, port, 5)
        loop.create_task(server)
        loop.run_forever()
