# Sample Session
Tested by transferring a 128 kbps joint stereo MP3 file of Rick Astley's 1987 hit song, Never Gonna Give You Up (about 3.25MB) From a Raspberry Pi to an ESP32-S3. The upload was successful, but took about twice as long to transfer as it would to play the song. Download is even slower at 08:20 (6.64 KiB/s). But, no errors and no stalls.

## tnftp Client on Raspberry Pi 2B
```
220 FTPdLite (MicroPython)
Name (192.168.10.57:pi): Felicia
331 Password required for Felicia.
Password:
230 Login successful.
Remote system type is UNIX.
Using binary mode to transfer files.
ftp> put Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
local: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3 remote: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
227 Entering passive mode =192,168,10,57,192,2
150 Transferring file.
100% |***********************************|  3327 KiB    8.95 KiB/s    00:00 ETA
226 Transfer finished.
3407402 bytes sent in 06:13 (8.90 KiB/s)
ftp> ls
227 Entering passive mode =192,168,10,57,192,3
150 /pub
-rw-rw-rw-  1  root  root     3407402  Nov 14 03:02  Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
226 Directory list sent.
ftp> site df
211-Filesystem      Size      Used     Avail   Use%
211 flash          6144K     3392K     2752K    55%
ftp> quit
221 Bye, Felicia.
```
_Figure 1: Over half my flash RAM dedicated to an elaborate Rick roll._

## FTPdLite Log Output on ESP32-S3 Serial Console
```
220 FTPdLite (MicroPython)
USER Felicia
331 Password required for Felicia.
PASS ********
230 Login successful.
SYST
215 UNIX Type: L8
FEAT
211
TYPE I
200 Always in binary mode.
EPSV
502 Command not implemented.
PASV
227 Entering passive mode =192,168,10,57,192,2
STOR Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
150 Transferring file.
226 Transfer finished.
TYPE A
200 Always in binary mode.
PASV
227 Entering passive mode =192,168,10,57,192,3
LIST
150 /pub
-rw-rw-rw-  1  root  root     3407402  Nov 14 03:02  Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
226 Directory list sent.
SITE df
Filesystem      Size      Used     Avail   Use%
flash          6144K     3392K     2752K    55%
QUIT
221 Bye, Felicia.
```
_Figure 2: Five hundred some odd lines of code committed just to sneak in Bye, Felicia_
