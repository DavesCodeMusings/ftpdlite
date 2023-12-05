# FTPdLite Administration
Microcontrollers are not multi-user systems.
* There's no /etc/passwd to track individual user accounts.
* Their flash file systems have no file ownership or permissions.
* There's no concept of runlevels or multi-user / single-user modes.
* They don't have much RAM or storage space.

All of this presents a unique challenge when trying to make a microcontroller behave like an FTP server. Below are the solutions offered by FTPdLite:

## User Accounts
FTPdLite can be setup with user accounts similar to a Unix-like system. This is done with the `add_credential()` method in _main.py_.

Here's a basic example:

```
server = FTPdLite()
server.add_credential("root:root:0:0:Super User:/root:/bin/nologin")
server.add_credential("ftp:ftp:65534:65534:Anonymous FTP:/pub:/bin/nologin")
```
_Figure 1: Example of two Unix-style accounts with cleartext passwords_

In the example above, the root and ftp user accounts are created in a style similar to what's used in a Unix-style /etc/passwd. It's also possible to create accounts using the simpler htpasswd-style as show below.

```
server.add_credential("craig:passw0rd")
server.add_credential("felicia:$5a$EbINmHbYCKCr0SAC$sBkCr6qrFPeQnZAp1y36lSrYieKghtbS1QTfGI5qkYM=")
```
_Figure 2: Example of two htpasswd-style accounts, one with cleartext and one with hashed password._

You can set up users either way. If you choose the simpler htpasswd style, the following defaults are applied to the accounts you create:
* The user ID (uid) is set to 65534 (nobody)
* The group ID (gid) is set to 65534 (nogroup)
* There's no home directory assigned

These defaults mean the user will have read-only access to the file system and cannot perform any privileged SITE commands.

## File System Permissions
There are no permissions native to the flash file system or any microSD cards you might choose to attach. To get around this limitation, FTPdLite uses a combination of user ID, group ID, and home directory for the account to determine if write access is allowed. The criteria is detailed below.
* If the account's UID is 0 (root user), writing is allowed anywhere.
* If the GID is 10 (wheel group), writing is allowed anywhere.
* If the account has a GID of 100 (users), the user is allowed to write to their home directory.
* All other UID/GID combinations are readonly, no writing is allowed.

Here are some scenarios to help it make sense:
* If you want a user that can write anything, anywhere, make the account with a UID of 0 (root).
* If you want multiple users who can write anywhere, but not have to share the root password, make their accounts with a GID of 10 (wheel).
* If you want multiple users who can write only to their home directories, make their accounts with GID 100 (users).
* If you want a read-only user who can't write anything at all, give them a UID that is not 0 and a GID that's not 0, 10, or 100.

To assign uid, gid, and home directory location, you must use `add_credential()` with the seven-field, colon-separated, Unix-style string.

```
server.add_credential("debbie:$5a$EbINmHbYCKCr0SAC$sBkCr6qrFPeQnZAp1y36lSrYieKghtbS1QTfGI5qkYM=:1001:100:/home/debbie:/bin/nologin")
```
_Figure 3: A user account with a gid of 100 (users), and a home directory._

## System Administration Privileges
There are also a number of SITE commands that anyone can use to perform system tasks like you might do at a shell prompt. Type `SITE help` to get a list with descriptions. The two that require privileged access are:
* `SITE kick` to forcibly disconnect a session.
* `SITE shutdown` to close down, deepsleep, or reboot the server.

A user account must have a UID of 0 (root) or a GID of 0 (root) for these privileged commands to succeed.

The _root_ user also has the ability to log in after `SITE shutdown` has been issued to tell the server to stop accepting connections. Any other users, including those with a GID of 0, will be denied when trying to log in.

Here's a scenario where you might use this functionality:

You want to shutdown the server, but you're concerned you might interrupt someone's file transfer.
1. Log in a _root_.
2. Issue the command `SITE shutdown` to block any new user logins.
3. Use `SITE who` to list any active connections.
4. Ask the users to log out, or let their idle session timeout, or use `SITE kick` to disconnect them.
5. Use `SITE shutdown -h` to put the microcontroller into deepsleep so you can unplug it or tap the RESET button.

Alternatively, you can use `SITE shutdown -r` to restart the microcontroller remotely.

Whenever a shutdown command is issued, file systems are sync'd first. This should help avoid corruption due to cached data that hasn't been written.

## Expanded Storage Space
The microcontroller's flash file system isn't big enough to store a lot of data. If you're intending to use FTPdLite to offer more than a handful of files, it's wise to attach a microSD card socket to the system. You'll get multiple gigabytes of cheap storage and you won't risk wear and tear on your microcontroller's flash RAM.

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

A helpful format is:
* What is the error or unexpected behavior?
* What can be done to recreate it?
* What should it be doing instead?

And remember, I am a project team of one part-time hobbyist, so please temper your expectations accordingly.
