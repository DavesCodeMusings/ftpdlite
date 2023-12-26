# FTPdLite Administration
Microcontrollers are not multi-user systems.
* There's no /etc/passwd to track individual user accounts.
* Their flash file systems have no file ownership or permissions.
* They don't have much storage space.

All of this presents a unique challenge when trying to make a microcontroller behave like an FTP server. Below are the solutions offered by FTPdLite:

## User Accounts
FTPdLite can be run without specifying user accounts. In this scenario, it acts like an anonymous FTP site. Anyone can log in without a password and download files, but no one has write access. Most people will want to set up at least one account.

Setting up accounts is done with the `add_account()` method in _main.py_.

Here's an example:

```
server = FTPd()
server.add_credential("root:root")
server.add_credential("ftp:ftp")
```
_Figure 1: Example of two accounts with cleartext passwords_

Accounts are created using the htpasswd style with the format of: username, a colon separator, and the password.

```
server.add_credential("felicia:$5a$EbINmHbYCKCr0SAC$sBkCr6qrFPeQnZAp1y36lSrYieKghtbS1QTfGI5qkYM=")
server.add_credential("craig:Passw0rd")
```
_Figure 2: Example of two accounts, the first with a hashed password._

## File System Permissions
The first user account created will be given read-write access to all files on the microcontroller's filesystem. Any additional accounts will be given read-only access. In the example of Figure 2 above, user _felicia_ can upload and download files, delete files, create and remove directories. User _craig_ can only download files.

## System Administration Privileges
There are also a number of SITE commands that anyone can use to perform system tasks like you might do at a shell prompt. Type `SITE help` to get a list with descriptions. There are also two that require privileged access are:
* `SITE kick` to forcibly disconnect a session.
* `SITE shutdown` to deepsleep or reboot the server.

Only the user with read-write access can perform these privileged actions.

## Expanded Storage Space
If you're intending to use FTPdLite to offer more than a handful of files, you can attach a microSD card socket to the system. With this, you'll get multiple gigabytes of cheap storage and you won't risk wear and tear on your microcontroller's flash RAM.

This bit of MicroPython in your _boot.py_ is an example of how to do that:
```
from machine import Pin, SDCard
from os import VfsFat, mount

SD_MOUNT = "/pub"
print(f"Mounting micro SD card on: {SD_MOUNT}")
sdcard = SDCard(slot=3, sck=Pin(12), miso=Pin(13), mosi=Pin(11), cs=Pin(10))
vfs = VfsFat(sdcard)
mount(vfs, SD_MOUNT)
```
_Figure 4: Mounting a FAT formatted, SPI interfaced microSD card_

The example above was taken from an ESP32-S3. You will need to adjust the pin assignments depending on your chosen microcontroller and your wiring.

## That's It!
Have fun with your FTP server. If you find any bugs, please create an issue at the [project site on GitHub](https://github.com/DavesCodeMusings/ftpdlite).

See [CONTRIBUTING.md](CONTRIBUTING.md) for more info. And remember, I am a project team of one part-time hobbyist, so please temper your expectations accordingly.
