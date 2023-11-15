# FTPdLite
_File systems in flight! FTPdLite!_

**FTPdLite is a work in progress. See Caveats below to adjust your expectations.**

## What is it?
FTPdLite is an FTP server written in MicroPython using asyncio. The goal is to provide easy access to files on a microcontroller's flash file system without dragging out a USB cable.

## Why should I care?
You shouldn't really. FTP is an I.T. security professional's worst nightmare. This project is really only of use in a lab environment. But, it's kind of neat to see the inner workings of one of the internet's earliest protocols.

## How can I use it?
First, read up on how insecure FTP is. Then, if you still want to do it...

Download ftpdlite.py and put it in your MicroPython device's /lib directory. Then run FTPdLite from main.py like the example shown below. You'll also need a boot.py to get your device on the network.

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

## Caveats
FTPdLite is a total alpha-quality product at the moment. It does not work with all clients.
* It's not multi-user capable. Even the same user on multiple simultaneous client connections is flaky.
* MicroPython lacks the `glob()` function, so no wildcard filenames or _mget_.
* Does not play well with FileZilla or WinSCP GUI clients. Not sure why. It's on the to-do list.
* Have not yet tested successfully with Windows' ftp.exe, though PORT data channel is supported.
* But hey, it works with wget and the tnftp client on Raspberry Pi OS. Woohoo!
