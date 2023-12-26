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
server = FTPd()
server.add_account("ftpadmin:changeme")
server.add_account("ftp:ftp")
wifi_ip_address = wlan.ifconfig()[0]
server.run(host=wifi_ip_address, debug=True)
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
There's nothing special here. Similar to dozens of other MicroPython libraries, you import a class from a module and instantiate it with a name. In this case, the name is _server_.

```
from ftpdlite import FTPd
server = FTPd()
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
You'll need the IP address of the interface where you want to serve FTP requests. This must be an address and not 0.0.0.0 (to specify any) as this will cause PASV transfers will break. The _debug_ option adds extra information to the serial console output. Set it to False or remove it to disable debug. The _idle_timeout_ option specifies the number of minutes a user session can be inactive before being disconnected.

```
wifi_ip_address = wlan.ifconfig()[0]
server.run(host=wifi_ip_address, debug=True, idle_timeout=60)
```
_Figure 5: Starting the FTP server_
