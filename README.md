# ftpdlite
_File systems in flight! FTPdLite!_

**FTPdLite is a work in progress. See Caveats below to adjust your expectations.**

## What is it?
FTPdLite is an FTP server written in MicroPython using asyncio. The goal is to provide easy access to files on a microcontroller's flash file system without dragging out a USB cable.

## Why should I care?
You shouldn't really. FTP is an I.T. security professional's worst nightmare. This project is really only of use in a lab environment. But, it's kind of neat to see the inner workings of one of the internet's earliest protocols.

## How can I use it?
First, read up on how insecure FTP is. Then, if you still want to do it...

Download ftpdlite.py and put it in your device's /lib directory. Then run FTPdLite from main.py like the example shown below. You'll also need a boot.py to get your device on the network.

main.py
```
from ftpdlite import FTPdLite

server = FTPdLite()
server.credentials = "username:password"
server.run(host=wlan.ifconfig()[0], debug=True)
```

Change the server.credentials to something that makes sense to you. Default credentials are _Felicia:Friday_

Boot your microcontroller and point your FTP client to port 21.

### MIP Install
MicroPython's mpremote provides a handy way to download the library as well.

```
py -m mpremote connect PORT mip install github:DavesCodeMusings/ftpdlite
```

## Caveats
FTPdLite is a total alpha-quality product at the moment. It lacks several important features.
* It currently does not play well with FileZilla. Not sure why. It's on the to-do list.
* It does not support PORT mode transfers that Windows command-line FTP expects. But, that's more of a Windows problem.
* MicroPython lacks the `glob()` function, so no wildcard filenames or _mget_.
* But, it works with the tnftp client on Raspberry Pi OS. Woohoo!
