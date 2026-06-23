# FTPdLite QuickStart
This guide shows how to get an FTPdLite server up and running with minimal fuss. All commands assume the use of MicroPython's MPRemote. Just replace _PORT_ with your microcontroller's COM port. For different development tools and operating system, please adjust accordingly.

## Install FTPdLite with MIP
```
mpremote connect PORT mip install github:DavesCodeMusings/ftpdlite
```

This downloads ftpdlite.mpy to the microcontroller's /lib directory.

## Upload boot.py
```
mpremote connect PORT cp 'boot.py' ':boot.py'
```

The goal of boot.py is to get the microcontroller attached to the network and set the time via NTP.

```
from network import WLAN, STA_IF
from ntptime import settime

wlan = WLAN(STA_IF)
wlan.active(True)
wlan.connect("ssid","password")
while not wlan.isconnected():
    pass
settime()
```
_Figure 1: boot.py_

## Upload main.py
```
mpremote connect PORT cp 'main.py' ':main.py'
```

The main.py file creates users and starts the FTP server.

```
from ftpdlite import FTPd
wifi_ip_address = wlan.ifconfig()[0]
server = FTPd(host=wifi_ip_address)
server.add_account("ftpadmin:changeme")
server.add_account("ftp:ftp")
server.run(debug=True)
```
_Figure 2: main.py_

## Boot the Server
Once you have the files uploaded and the credentials for WiFi and FTP users in place, you're ready to press RESET and boot the FTP server. Watch the serial console for informational messages.

That's it. Fire up your FTP client, log in as _ftpadmin_ and start FTPing.

## Appendix: Deconstructing main.py
There are three distinct sections in main.py.
1. Creating a server instance
2. Adding user credentials
3. Starting the server 

### Creating a server instance
Similar to dozens of other MicroPython libraries, you import a class from a module and instantiate it with a name. In this case, the name is _server_.

You must provide an address value to _host_, otherwise your server will only listen on 127.0.0.1. This must be an actual address and not 0.0.0.0 (to specify any) as this will cause PASV transfers will break.

```
from ftpdlite import FTPd
wifi_ip_address = wlan.ifconfig()[0]
server = FTPd(host=wifi_ip_address)
```
_Figure 3: Creating the server instance_

### Adding user accounts
User accounts are written htpasswd-style, with the username, a colon separator, and the password. In the sample main.py, there are two accounts.

```
server.add_account("ftpadmin:changeme")
server.add_account("ftp:ftp")
```
_Figure 4: Creating multiple user accounts_

When creating user accounts, the first account created will have read-write access. Any remaining accounts will be restricted to read-only. The account names don't matter, only the order of creation.

### Starting the server
The `run()` method will start up the server and listen for connections. The _debug_ parameter is optional and defaults to _False_ if not specified.

```
server.run(debug=True)
```
_Figure 5: Starting the FTP server_
