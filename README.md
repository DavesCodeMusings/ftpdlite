# FTPdLite
_File systems in flight! FTPdLite!_

**FTPdLite is a work in progress. See Caveats below to adjust your expectations.**

## What is it?
FTPdLite is an FTP server written in MicroPython using asyncio. The goal is to provide easy access to files on a microcontroller's flash file system without dragging out a USB cable.

## Why should I care?
You shouldn't really. FTP is an I.T. security professional's worst nightmare. This project is really only of use in a lab environment. But, it's kind of neat to see the inner workings of one of the internet's earliest protocols.

## How can I use it?
First, read up on how insecure FTP is. Then, if you still want to do it...

Download ftpdlite.py and put it in your MicroPython device's /lib directory (or see below for MIP install.) Then run FTPdLite from main.py like the example shown below. You'll also need a boot.py to get your device on the network.

main.py
```
from ftpdlite import FTPdLite

server = FTPdLite()
server.credentials = "username:password"
server.run(host=wlan.ifconfig()[0])
```

Change the server.credentials to something that makes sense to you. Default credentials are _Felicia:Friday_

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
FTPdLite works best with command-line clients.
* The _tnftp_ package on Linux provides an outstanding FTP experience.
* Windows _ftp.exe_ works, but has a limited command set and no PASV mode is a problem for firewalls.
* For non-interactive transfers, _wget_ works well, as does _curl_.

## Caveats
FTPdLite is a total alpha-quality product at the moment.
* It's not multi-user capable. Limited to one login session per client IP address.
* MicroPython lacks the `glob()` function, so no wildcard filenames or _mget_.
* GUI clients (FileZilla, et al.) must have simultaneous connections limited to 1.
