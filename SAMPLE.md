# Sample Sessions
My standard stress test is transferring a 128 kbps joint stereo MP3 file of Rick Astley's 1987 hit song, Never Gonna Give You Up (about 3.25MB) to and from FTPdLite on an ESP32-S3 using various clients.

The upload is successful, but not speedy, at about 30 kB/sec. Download is twice as fast, at up to 70 kB/sec. It's kind of like Napster on a 56k modem. But, no errors and no stalls, so I'd call it a win.

For all tests, the ESP32-S3 was on a separate IoT network behind a firewall, except where noted.

## Passive FTP Transfer with tnftp Client
Using a Raspberry Pi 2B with Raspberry Pi OS Lite (no-GUI) and a command-line client, I uploaded to the ESP32 and then downloaded again.

### Interactive FTP Session Screen Capture
```
$ ftp 192.168.10.57
Connected to 192.168.10.57
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
_Figure 1: Over half my flash RAM dedicated to an elaborate Rick roll_

### FTPdLite Log Output on the ESP32-S3 Serial Console
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
_Figure 2: Seven hundred some odd lines of code committed just to sneak in Bye, Felicia_

## Windows ftp.exe Behind a Firewall
```
C:\> ftp 192.168.10.57
Connected to 192.168.10.57.
220 FTPdLite (MicroPython)
200 Always in UTF8 mode.
User (192.168.10.57:(none)): Felicia
331 Password required for Felicia.
Password:
230 Login successful.
ftp> cd /pub
250 /pub
ftp> ls
200 OK.
150 /pub
```

_Figure 3: The data connection just hangs, proving 1990s technology still sucks._

## Downloading Again to Test Active FTP Transfers
I also used tnftp with the -A option to use only Active FTP data connections. This is to test FTPdLite's handling of the PORT command. For this test, the ESP32 was moved to the same network as the client, so there was no firewall in-between. To be fair, ftp.exe works too when there's no firewall in-between, and the transfer speed is decent.

### Active FTP transfer Screen Capture
```
$ ftp -A 192.168.10.57
Connected to 192.168.10.57.
220 FTPdLite (MicroPython)
Name (192.168.10.57:pi): Felicia
331 Password required for Felicia.
Password:
230 Login successful.
Remote system type is UNIX.
Using binary mode to transfer files.
ftp> cd /pub
250 /pub
ftp> get Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
local: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3 remote: Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
200 OK.
150 Transferring file.
  3327 KiB   74.52 KiB/s
226 Transfer finished.
3407402 bytes received in 00:44 (74.52 KiB/s)
```

_Figure 4: Successful transfer using archaic and firewall unfriendly Active FTP_

### Active FTP Serial Console Log
```
220 FTPdLite (MicroPython)
USER Felicia
331 Password required for Felicia.
PASS ********
230 Login successful.
SYST
215 UNIX Type: L8
FEAT
211-Extensions supported:
211-SIZE
211 END
CWD /pub
250 /pub
TYPE I
200 Always in binary mode.
EPRT |1|192.168.10.53|54671|
502 Command not implemented.
PORT 192,168,10,53,213,143
Port address: 192,168,10,53,213,143
Opening data connection to: 192.168.10.53:54671
200 OK.
RETR Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
150 Transferring file.
226 Transfer finished.
```

_Figure 5: Log output showing PORT command in case you didn't believe me._

## Non-Interactive Transfer
Using curl or wget is handy for scripted transfers, so I tested that too. The wget download was nearly ten seconds faster than tnftp, so if you need to get your groove on in a hurry, you know your go-to client.

### Using curl
```
$ curl -u Felicia:Friday ftp://192.168.10.57//pub/Rick_Astley_-_Never_Gonna_Give_You_Up.mp3 --output Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 3327k  100 3327k    0     0  66505      0  0:00:51  0:00:51 --:--:-- 64074
```

_Figure 6: Not quite as fast as tnftp_

### Using wget
```
$ wget --ftp-user=Felicia --ftp-password=Friday ftp://192.168.10.57//pub/Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
--2023-11-14 19:57:40--  ftp://192.168.10.57//pub/Rick_Astley_-_Never_Gonna_Give_You_Up.mp3
           => ‘Rick_Astley_-_Never_Gonna_Give_You_Up.mp3’
Connecting to 192.168.10.57:21... connected.
Logging in as Felicia ... Logged in!
==> SYST ... done.    ==> PWD ... done.
==> TYPE I ... done.  ==> CWD (1) /pub ... done.
==> SIZE Rick_Astley_-_Never_Gonna_Give_You_Up.mp3 ... 3407402
==> PASV ... done.    ==> RETR Rick_Astley_-_Never_Gonna_Give_You_Up.mp3 ... done.
Length: 3407402 (3.2M) (unauthoritative)

Rick_Astley_-_Never 100%[===================>]   3.25M  71.8KB/s    in 46s

2023-11-14 19:58:28 (72.6 KB/s) - ‘Rick_Astley_-_Never_Gonna_Give_You_Up.mp3’ saved [3407402]
```

_Figure 7: Winner of the speedy download crown, it's wget!_
