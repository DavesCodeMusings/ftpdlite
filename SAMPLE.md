# Sample Session
Tested by transferring a 128 kbps joint stereo MP3 file of Rick Astley's 1987 hit song, Never Gonna Give You Up (about 3.25MB) from a Raspberry Pi to an ESP32-S3. The upload was successful, but not speedy at about 30 kB/sec. Download is twice as fast at about 60 kB/sec. It's kind of like Napster on a 56k modem. But, no errors and no stalls.

## tnftp Client on the Raspberry Pi 2B
```
220 FTPdLite (MicroPython)
Name (192.168.10.57:pi): Felicia
331 Password required for Felicia.
Password:
230 Login successful.
Remote system type is UNIX.
Using binary mode to transfer files.
ftp> cd /pub
250 /pub
ftp> put Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
local: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3 remote: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
227 Entering passive mode =192,168,10,57,192,0
150 Transferring file.
100% |***********************************|  3327 KiB   28.98 KiB/s    00:00 ETA
226 Transfer finished.
3407402 bytes sent in 01:55 (28.80 KiB/s)
ftp> ls
227 Entering passive mode =192,168,10,57,192,1
150 /pub
-rw-rw-rw-  1  root  root     3407402  Nov 14 18:52  Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
226 Directory list sent.
ftp> get Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
local: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3 remote: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
227 Entering passive mode =192,168,10,57,192,2
150 Transferring file.
  3327 KiB   60.45 KiB/s
226 Transfer finished.
3407402 bytes received in 00:55 (60.45 KiB/s)
ftp> quit
221 Bye, Felicia.
```
_Figure 1: Over half my flash RAM dedicated to an elaborate Rick roll._

## FTPdLite Log Output on the ESP32-S3 Serial Console
```
Listening on 192.168.10.57:21
220 FTPdLite (MicroPython)
USER Felicia
331 Password required for Felicia.
PASS ********
230 Login successful.
SYST
215 UNIX Type: L8
FEAT
211
CWD /pub
250 /pub
TYPE I
200 Always in binary mode.
EPSV
502 Command not implemented.
PASV
227 Entering passive mode =192,168,10,57,192,0
STOR Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
150 Transferring file.
226 Transfer finished.
TYPE A
200 Always in binary mode.
PASV
227 Entering passive mode =192,168,10,57,192,1
LIST
150 /pub
-rw-rw-rw-  1  root  root     3407402  Nov 14 18:52  Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
226 Directory list sent.
TYPE I
200 Always in binary mode.
PASV
227 Entering passive mode =192,168,10,57,192,2
RETR Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
150 Transferring file.
226 Transfer finished.
QUIT
221 Bye, Felicia.
```
_Figure 2: Five hundred some odd lines of code committed just to sneak in Bye, Felicia_
