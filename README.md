# FTPdLite
_File systems in flight! FTPdLite!_

**FTPdLite is a work in progress. See Caveats below to adjust your expectations.**

Important update! FTPdLite now has no default user account and starts in readonly mode. See _How can I use it?_ below for configuration steps.

## What is it?
FTPdLite is an FTP server written in MicroPython using asyncio. The goal is to provide easy access to files on a microcontroller's flash file system without dragging out a USB cable.

## Why should I care?
You shouldn't really. FTP is an I.T. security professional's worst nightmare. This project is really only of use in a lab environment. But, it's kind of neat to see the inner workings of one of the internet's earliest protocols.

## How can I use it?
First, read up on how insecure FTP is. Then, if you still want to do it...

Download ftpdlite.py and put it in your MicroPython device's /lib directory (or see below for MIP install.) Then run FTPdLite from main.py like the example shown below.

>You'll also need a boot.py to get your device connected to the network and set the correct time with NTP.

```
from ftpdlite import FTPdLite

wifi_ip_address = wlan.ifconfig()[0]
server = FTPdLite(readonly=False)
server.add_credential("root:root:0:0:Super User:/:/bin/nologin")
server.add_credential("Felicia:Friday")
server.add_credential("ftp:ftp")

server.run(host=wifi_ip_address, debug=True)
```
_Figure 1: main.py_

If you want people to be able to upload files and make directories, pay attention to the _readonly=False_ part of `server = FTPdLite(readonly=False)` default behavior is readonly mode.

Add server.credentials for whatever users make sense to you. `add_credential()` will take either htpasswd-style or Unix-style password entries. There are a few things to keep in mind:

* Some commands, like `site kick` and `site reboot`, are only authorized for an account with a group id of 0. (That's the second 0 in _root:root:0:0:Super User:/:/bin/nologin_)
* htpasswd-style credentials are automatically assigned to gid 1000. So no privileged access.
* The Unix-style GECOS, home, and login shell fields are just place holders. They have no effect on anything.
* Password encryption is not supported... yet.
* **There are no defaults user accounts. You must add at least one credential or you can't log in.**

Boot your microcontroller and point your FTP client to port 21.

```
wget --ftp-user=Felicia --ftp-password=Friday ftp://192.168.1.100//pub/Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
```

### MIP Install
MicroPython's mpremote provides a handy way to download the library as well.

```
py -m mpremote connect PORT mip install github:DavesCodeMusings/ftpdlite
```

## Supported Clients
FTPdLite works best with these clients:
* The _tnftp_ package on Linux provides an outstanding FTP experience.
* FileZilla (with simultaneous connections set to 1) is the go-to choice for Windows.
* Windows _ftp.exe_ works, but has a limited command set and its lack of PASV mode presents a problem for firewalls.
* For non-interactive transfers, _wget_ works well, as does _curl_.

## Caveats
FTPdLite is a total alpha-quality product at the moment.
* It is multi-user capable, but it's limited to one login session per client IP address.
* MicroPython lacks the `glob()` function, so no wildcard filenames or _mget_.
* GUI clients (FileZilla, et al.) must have simultaneous connections limited to 1.
