# FTPdLite QuickStart
This guide shows how to get an FTPdLite server up and running with minimal fuss. All commands assume the use of MicroPython's MPRemote on a Windows system. Just replace _PORT_ with your microcontroller's COM port. For different development tools and operating system, please adjust accordingly.

## Install FTPdLite with MIP
```
mpremote connect PORT mip install github:DavesCodeMusings/ftpdlite
```

This downloads ftpdlite.py to the microcontroller's /lib directory.

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
from ftpdlite import FTPdLite
server = FTPdLite()

server.add_credential("ftp:ftp")
server.add_credential("root:Passw0rd:0:0:Super User:/:/bin/nologin")
server.add_credential("felicia:$5a$gQt7ogusrX6DdrW4$OzJTc5KO9MljuwSUcV797EnAt8UzcKjCESWPziT5PV4=")

wifi_ip_address = wlan.ifconfig()[0]
server.run(host=wifi_ip_address, debug=True)
```
_Figure 2: main.py_

## Boot the Server
Once you have the files uploaded and the credentials for WiFi and FTP users in place, you're ready to press RESET and boot the FTP server. Watch the serial console for informational messages.

That's it. Fire up your FTP client and start FTPing.

## Appendix: Deconstructing main.py
There are three distinct sections in main.py.
1. Creating a server instance
2. Adding user credentials
3. Starting the server 

### Creating a server instance
There's nothing special here. Similar to dozens of other MicroPython libraries, you import a class from a module and instantiate it with a name. In this case, the name is _server_.

```
from ftpdlite import FTPdLite
server = FTPdLite()
```

### Adding user credentials
FTPdLite gives you different ways to create users. You can pick and choose based on your needs.

First is the htpasswd-style. This is the simplest. It creates a user with readonly access to the FTP server and a cleartext password.
```
server.add_credential("ftp:ftp")
```

Next is the Unix-style. This allows you to specify a UID and GID for the user. Users with GID 0 are given write access to the FTP server and can run commands to manage the server and its user sessions.
```
server.add_credential("root:Passw0rd:0:0:Super User:/:/bin/nologin")
```

Finally there is the hashed password. This allows you to protect password information on the flash filesystem. Both htpasswd-style and Unix-style can use the hashed password.
```
server.add_credential("felicia:$5a$gQt7ogusrX6DdrW4$OzJTc5KO9MljuwSUcV797EnAt8UzcKjCESWPziT5PV4=")
```

>Note: FTP will send usernames and passwords in cleartext and hashing can't help with that.

### Starting the server
You'll need the IP address of the interface where you want to serve FTP requests. This must be an address and not 0.0.0.0 (to specify any) as this will cause PASV transfers will break. The _debug_ option adds extra information to the serial console output. Set it to False or remove it to disable debug. The _idle_timeout_ option specifies the number of minutes a user session can be inactive before being disconnected.

```
wifi_ip_address = wlan.ifconfig()[0]
server.run(host=wifi_ip_address, debug=True, idle_timeout=60)
```
