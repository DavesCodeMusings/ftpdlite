# FTPdLite
_File systems in flight... FTPdLite!_

**FTPdLite is a work in progress. See Caveats below to adjust your expectations.**

## What is it?
FTPdLite is an FTP server written in MicroPython using asyncio. The goal is to provide easy access to files on a microcontroller's flash file system without dragging out a USB cable. Or you can actually use it as a small, home FTP server.

## Why should I care?
You shouldn't really. FTP is an I.T. security professional's worst nightmare. This project is really only of use in a lab environment. But, it's kind of neat to see the inner workings of one of the internet's earliest protocols.

## How can I use it?
First, read up on how insecure FTP is. Then, if you still want to do it... 

Refer to the QUICKSTART guide for installation details.

## Supported Clients
FTPdLite works best with these clients:
* The _tnftp_ package on Linux provides an outstanding FTP experience.
* Gnome VFS FTP client has been reported to work as well.
* _FileZilla_ (with simultaneous connections set to 1) is the go-to choice for Windows.
* Windows _ftp.exe_ works, but has a limited command set and its lack of PASV mode presents a problem for firewalls.
* For non-interactive transfers, _wget_ works well, as does _curl_.

## Caveats
FTPdLite is a total alpha-quality product at the moment.
* It is multi-user capable, but it's limited to one login session per client IP address.
* MicroPython lacks the `glob()` function, so no wildcard filenames or _mget_.
* GUI clients (FileZilla, et al.) must have simultaneous connections limited to 1.
