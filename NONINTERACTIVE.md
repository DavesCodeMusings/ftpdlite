# Minimalist, Noninteractive FTP
Many times when using FTP, you'll use a client like FileZilla or ftp.exe. These allow you to log in, browse directories, upload and download files, etc. But, it's also possible to use FTP programatically, either with Python's ftplib or a command-line utility like curl or wget. In these cases, you're probably only concerned with uploading (put) and downloading (get).

If your only use case is for scripted FTP transactions, FTPdLite offeres a minimalist class to do just that. See the example below.

```
from ftpdlite import FTPdLite
server = FTPdLite()
server.add_account("ftpadmin:changeme")
server.add_account("ftp:ftp")
wifi_ip_address = wlan.ifconfig()[0]
server.run(host=wifi_ip_address, debug=True)
```
_Figure 1: main.py_

This is almost exactly the same as the main.py detailed in [QUICKSTART.md](QUICKSTART.md), with one small change. The class name _FTPd_ has been replaced with _FTPdLite_ on the first and second lines.

FTPdLite offers a subset of the usual FTP commands. To get an idea of what this means, take a look at RFC-959, Section 5.1: Minimum Implementation. FTPdLite offers the commands specified there, plus PASS (passwords) for added security and PASV (passive mode) to work with firewalls.

What this means is, you'll have to use the full path when uploading or downloading files. You can't create or change directories using an FTP client. You can't delete files. But, if all you want to do is say, fetch data logged by your microcontroller with a cron job on a server, this could work.

One-line command-line downloads are easy.

```
curl ftp://192.168.10.55/main.py
wget ftp://192.168.10.55/main.py
```
_Figure 2: Command-line download examples_

Uploads can be done as well.

```
curl -u ftpadmin --upload-file ANNOUNCE.md ftp://192.168.10.55/test.txt
Enter host password for user 'ftpadmin': ********
```
_Figure 2: Command-line upload using curl_

