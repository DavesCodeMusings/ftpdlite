# FTPdLite
_File systems in flight... FTPdLite!_

**FTPdLite is a work in progress. See Caveats below to adjust your expectations.**

## What is it?
FTPdLite is an FTP server written in MicroPython using asyncio. The goal is to provide easy access to files on a microcontroller's flash file system without dragging out a USB cable. Or you can actually use it as a small, home FTP server.

## Why should I care?
You shouldn't really. FTP is an I.T. security professional's worst nightmare. This project is really only of use in a lab environment. But, it's kind of neat to see the inner workings of one of the internet's earliest protocols.

## How can I use it?
First, read up on how insecure FTP is. Then, if you still want to do it...

### Install It
Download ftpdlite.py and put it in your MicroPython device's /lib directory (or see below for MIP install.) Then run FTPdLite from main.py like the example shown below.

```
from ftpdlite import FTPdLite

wifi_ip_address = wlan.ifconfig()[0]
server = FTPdLite()
server.add_credential("root:root:0:0:Super User:/:/bin/nologin")
server.add_credential("Felicia:Friday")
server.add_credential("ftp:ftp")

server.run(host=wifi_ip_address, debug=True)
```
_Figure 1: Sample main.py_

>MicroPython's mpremote provides a handy way to download the library as well.
>```
>py -m mpremote connect PORT mip install github:DavesCodeMusings/ftpdlite
>```

You'll also need a boot.py to get your device connected to the network and set the correct time with NTP.

```
from network import hostname, WLAN, STA_IF
from ntptime import settime
from time import ticks_diff, ticks_ms, sleep
from config import HOSTNAME, WIFI_NAME, WIFI_PASS, WIFI_TIMEOUT

hostname(HOSTNAME)
wlan = WLAN(STA_IF)
wlan.active(True)

print(f"Connecting to SSID {WIFI_NAME}...", end='')
wlan.connect(WIFI_NAME, WIFI_PASS)
start_time = ticks_ms()
while not wlan.isconnected():
    if ticks_diff(ticks_ms(), start_time) > WIFI_TIMEOUT * 1000:
        print(".", end='')
        sleep(1)
if not wlan.isconnected():
    print("Connection timed out.")
else:
    print(f"\n{wlan.ifconfig()[0]}")
    settime()  # Using NTP time prevents odd timestamps on files.
```
_Figure 2: Sample boot.py_

### Configure Users

**There are no default user accounts. You must add at least one credential or you can't log in.**

Add server.credentials for whatever users make sense to you. `add_credential()` will take either Unix-style or htpasswd-style password entries.

```
server.add_credential("root:root:0:0:Super User:/:/bin/nologin")  # Unix-style
server.add_credential("ftp:ftp")  # htpasswd-style
```
_Figure 3: Examples of adding accounts_

The flash filesystem has no concept of permissions, so FTPdLite denies write access for everyone, except accounts with a group id of 0.

If you want people to be able to upload files and make directories, you need to use the Unix-tyle credential and assign the root (gid 0) group. (That's the second 0 in _root:root:0:0:Super User:/:/bin/nologin_ example above.)

There are some things to keep in mind:
* htpasswd-style credentials are automatically assigned to gid 65534. So no write access.
* Some commands, like `site kick` and `site reboot`, are only authorized for privileged accounts (group id 0).
* The Unix-style GECOS, home, and login shell fields are just place holders. They have no effect on anything.
* Password encryption is not supported... yet.

### Start Your FTP Server
Boot your microcontroller and point your FTP client to port 21.

```
wget --ftp-user=ftp --ftp-password=ftp ftp://192.168.1.100//pub/Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
```
_Figure 4: Fetching a File Non-Interactively_

## Supported Clients
FTPdLite works best with these clients:
* The _tnftp_ package on Linux provides an outstanding FTP experience.
* _FileZilla_ (with simultaneous connections set to 1) is the go-to choice for Windows.
* Windows _ftp.exe_ works, but has a limited command set and its lack of PASV mode presents a problem for firewalls.
* For non-interactive transfers, _wget_ works well, as does _curl_.

## Caveats
FTPdLite is a total alpha-quality product at the moment.
* It is multi-user capable, but it's limited to one login session per client IP address.
* MicroPython lacks the `glob()` function, so no wildcard filenames or _mget_.
* GUI clients (FileZilla, et al.) must have simultaneous connections limited to 1.
