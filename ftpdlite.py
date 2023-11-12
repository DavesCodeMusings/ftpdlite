### File systems in flight. FTPdLite! ###
# Many thanks to https://cr.yp.to/ftp.html for a clear explanation of FTP.
from asyncio import get_event_loop, sleep_ms, start_server
from os import chdir, getcwd, listdir, mkdir, rmdir, stat
from time import localtime

class FTPdLite:
    """
    A minimalist FTP server for MicroPython.
    """
    def __init__(self, request_buffer_size=1024):
        self.server_name = "FTPdLite (MicroPython)"
        self.credentials = "Felicia:Friday"
        self.request_buffer_size = request_buffer_size
        self.pasv_port_pool = list(range(49152, 49407))
        self.command_dictionary = {
            "CWD": self.cwd,
            "FEAT": self.feat,
            "HELP": self.help,
            "LIST": self.list,
            "MKD": self.mkd,
            "NLST": self.nlst,
            "NOOP": self.noop,
            "OPTS": self.opts,
            "PASS": self.passwd,
            "PASV": self.pasv,
            "PWD": self.pwd,
            "QUIT": self.quit,
            "RMD": self.rmd,
            "SYST": self.syst,
            "USER": self.user
        }

    def date_format(self, seconds, short=True):
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        datetime = localtime(seconds)
        month = months[datetime[1] - 1]
        day = datetime[2]
        day_space = ' ' if day < 10 else ''
        year = datetime[0]
        hour = datetime[3]
        hour_padding = '0' if hour < 10 else ''
        minute = datetime[4]
        minute_padding = '0' if minute < 10 else ''
        if short is True:
            output = '{} {}{} {}{}:{}{}'.format(month, day_space, day, hour_padding, hour, minute_padding, minute)        
        else:
            output = '{} {}{}, {} {}{}:{}{}'.format(month, day_space, day, year, hour_padding, hour, minute_padding, minute)
        return output

    """
    Get a TCP port number from the pool, then rotate the list to ensure
    it won't be used again for a while.
    """
    def get_pasv_port(self):
        port = self.pasv_port_pool.pop(0)
        self.pasv_port_pool.append(port)
        return port

    def parse_request(self, req_buffer):
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
        if code == 250 and msg is None:
            msg = "OK."
        print(f"{code} {msg}")
        writer.write(f"{code} {msg}\r\n")
        await writer.drain()

    # Each command function returns a boolean to indicate if session should be maintained or ended.
    async def cwd(self, dir, writer):
        if dir.startswith("/") is False:
            dir = getcwd() + "/" + dir
        try:
            chdir(dir)
        except OSError:
            await self.send_response(550, "No such directory.", writer)
        else:
            await self.send_response(250, getcwd(), writer)
        return True
    
    async def feat(self, _, writer):
        await self.send_response(211, "", writer)  # No features.
        return True

    async def help(self, topic, writer):
        await self.send_response(211, "[FTPdLite](https://github.com/DavesCodeMusings/ftpdlite)", writer)
        return True

    async def list(self, dir, writer):
        await sleep_ms(1000)  # kluge to wait for data connection to be ready
        if dir is None:
            dir = getcwd()
        elif dir.startswith("/") is False:
            dir = getcwd() + "/" + dir
        try:
            dir_entries = listdir(dir)
        except OSError:
            await self.send_response(451, "Unable to read directory.", writer)
        else:
            await self.send_response(150, dir, writer)
            for entry in dir_entries:
                properties = stat(dir + "/" + entry)
                if properties[0] & 0x4000:  # entry is a directory
                    type = 'd'
                    size = 0
                else:
                    type = '-'
                    size = properties[6]
                mtime = self.date_format(properties[8])
                formatted_entry = f"{type}rw-r--r--  1  root  root  {size:10d}  {mtime:>11s}  {entry}\r\n"
                print(formatted_entry)
                self.data_writer.write(formatted_entry)
            await self.data_writer.drain()
            await self.send_response(226, "Directory list sent. Closing data connection.", writer)
            self.data_writer.close()
            await self.data_writer.wait_closed()
            del self.data_writer
            self.data_reader.close()
            await self.data_reader.wait_closed()
            del self.data_reader
            if (self.debug):
                print("Data connection closed.")     
        return True

    async def nlst(self, dir, writer):
        await sleep_ms(1000)  # kluge to wait for data connection to be ready
        if dir is None:
            dir = getcwd()
        elif dir.startswith("/") is False:
            dir = getcwd() + "/" + dir
        try:
            dir_entries = listdir(dir)
        except OSError:
            await self.send_response(451, "Unable to read directory.", writer)
        else:
            await self.send_response(150, dir, writer)
            print("\n".join(dir_entries))
            self.data_writer.write("\r\n".join(dir_entries) + "\r\n")
            await self.data_writer.drain()
            await self.send_response(226, "Directory list sent. Closing data connection.", writer)
            self.data_writer.close()
            await self.data_writer.wait_closed()
            del self.data_writer
            self.data_reader.close()
            await self.data_reader.wait_closed()
            del self.data_reader
            if (self.debug):
                print("Data connection closed.")     
        return True

    async def mkd(self, dir, writer):
        if dir.startswith("/") is False:
            dir = getcwd() + "/" + dir
        try:
            mkdir(dir)
            await self.send_response(250, f"\"{dir}\"", writer)
        except OSError:
            await self.send_response(550, "Failed to create directory.", writer)
        return True

    async def noop(self, _, writer):
        await self.send_response(200, "Take your time. I'll wait.", writer)
        return True

    async def opts(self, string, writer):
        if string.upper() == "UTF8 ON":
            await self.send_response(200, "Always in UTF8 mode.", writer)
        else:
            await self.send_response("504 Unknown option.", writer)
        return True

    async def passwd(self, password, writer):
        if self.debug:
            print("Expecting:", self.credentials)
            print(f"Got: {self.username}:{password}")
        if self.username == self.credentials.split(":", 1)[0] and password == self.credentials.split(":", 1)[1]:
            await self.send_response(230, "Login successful.", writer)
            return True
        else:
            await self.send_response(430, "Invalid username or password.", writer)
            return False

    async def pasv(self, _, writer):
        host_octets = self.host.replace('.', ',')
        port = self.get_pasv_port()
        port_octet_high = port // 256
        port_octet_low = port % 256
        if self.debug:
            print(f"Starting data listener on port: {self.host}:{port}")
        loop = get_event_loop()
        data_listener = start_server(self.on_data_connect, self.host, port, 1)
        await loop.create_task(data_listener)
        await self.send_response(227, f"Entering passive mode ={host_octets},{port_octet_high},{port_octet_low}", writer)
        return True

    async def pwd(self, _, writer):
        await self.send_response(257, f"\"{getcwd()}\"", writer)
        return True

    async def quit(self, _, writer):
        await self.send_response(221, f"Bye, {self.username}.", writer)
        return False

    async def rmd(self, dir, writer):
        if dir.startswith("/") is False:
            dir = getcwd() + "/" + dir
        try:
            rmdir(dir)
            await self.send_response(250, "OK.", writer)
        except OSError:
            await self.send_response(550, "No such directory.", writer)
        return True

    async def syst(self, _, writer):
        await self.send_response(215, "UNIX Type: L8", writer)
        return True

    async def user(self, username, writer):
        self.username = username
        await self.send_response(331, f"Password required for {self.username}.", writer)
        return True

    async def on_data_connect(self, data_reader, data_writer):
        client_ip = data_writer.get_extra_info('peername')[0]
        if self.debug:
            print("Data connection from:", client_ip)
        self.data_reader = data_reader
        self.data_writer = data_writer

    async def on_ctrl_connect(self, ctrl_reader, ctrl_writer):
        client_ip = ctrl_writer.get_extra_info('peername')[0]
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
        if (self.debug):
            print(f"Control connection closed for {client_ip}")

    def run(self, host='0.0.0.0', port=21, debug=False):
        self.host = host
        self.debug = debug
        print(f'Listening on {host}:{port}')
        loop = get_event_loop()
        server = start_server(self.on_ctrl_connect, host, port, 5)
        loop.create_task(server)
        loop.run_forever()
