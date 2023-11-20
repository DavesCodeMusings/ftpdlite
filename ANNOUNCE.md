# FTPdLite
I've been working on an async FTP server and I thought I'd share. It's mostly for my own education, but it could be useful for some folks.

## What is it?
A minimalist, mostly RFC 959 compliant, asyncio FTP server for MicroPython-based microcontrollers.

## How do I get it?
You can use mpremote mip install github:DavesCodeMusings/ftpdlite

Or you can visit the project site at https://github.com/DavesCodeMusings/ftpdlite/

## For the love of God, man... why?
FTP is one of the earliest internet protocols. It's a security nightmare, but it's a pretty straightforward way to get files from point A to point B. And MicroPython asyncio is something I've been interested in learning more about. So, why not?

>Plus, There's only about nine and a half hours of daylight this time of year. I need something to keep my sanity.

## What else is there?
It's probably got bugs I don't know about, but for the case of a single user uploading and downloading files, it works. Tested clients include: _FileZilla_ (with simultaneous connections set to 1), _curl_, _wget_, and  _tnftp_. (Windoze _ftp.exe_ works too, but not behind a firewall.)

Using asyncio means it does handle multiple sessions, but only one session per client IP address. So still limited in some ways.

There are some extra features built into the SITE command. Together with the _tnftp_ client's extra commands, it makes for a rather sublime remote file management experience. The sample session below demonstrates some of the functionality.

## Sample Session

```
pi@raspberrypi:~ $ man ftp | head -5
TNFTP(1)                  BSD General Commands Manual                 TNFTP(1)

NAME
     tnftp — Internet file transfer program

pi@raspberrypi:~ $ ftp 192.168.10.57
Connected to 192.168.10.57.
220 FTPdLite (MicroPython)
Name (192.168.10.57:pi): Felicia
331 Password required for Felicia.
Password:
230 Login successful.
Remote system type is UNIX.
Using binary mode to transfer files.
ftp> pwd
Remote directory: /
ftp> ls
227 Entering passive mode =192,168,10,57,192,8
150 /
-rw-r--r--  1  root  root         629  Jan  1  2000  boot.py
-rw-r--r--  1  root  root         156  Jan  1  2000  config.py
-rw-r--r--  1  root  root         564  Nov 18 01:06  device_specs.py
drwxr-xr-x  1  root  root           0  Jan  1  2000  lib/
-rw-r--r--  1  root  root         117  Nov 18 01:06  main.py
drwxr-xr-x  1  root  root           0  Jan  1  2000  pub/
226 Directory list sent.
ftp> cd /pub
250 /pub
ftp> ls
227 Entering passive mode =192,168,10,57,192,1
150 /pub
-rw-r--r--  1  root  root     3407402  Nov 18 01:12  Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
-rw-r--r--  1  root  root          21  Nov 18 01:06  test.txt
226 Directory list sent.
ftp> less test.txt
This is a test file.
ftp> site df
211-Filesystem        Size        Used       Avail   Use%
211-flash          6144KiB     3428KiB     2716KiB    56%
211 End.
ftp> site free
211-         Total       Used      Avail
211-Mem:    133KiB      52KiB      80KiB
211 End.
ftp> site gc
211 OK.
ftp> site free
211-         Total       Used      Avail
211-Mem:    133KiB      26KiB     106KiB
211 End.
ftp> rstat
211-FTPdLite (MicroPython)
211-System date: Nov 18 15:43
211-Uptime: 0 days, 01:25
211-Number of users: 1
211-Connected to: ftpdlite
211-Logged in as: Felicia
211-TYPE: L8, FORM: Nonprint; STRUcture: File; transfer MODE: Stream
211 End.
ftp> quit
221 Bye, Felicia.
```
