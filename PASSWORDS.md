# User Passwords
FTPdLite give you the option of cleartext or hashed passwords. Cleartext is the most straightforward, but least secure. Cleartext passwords are visible to anyone who can view _main.py_ and this includes all users with an account. (Hint: they can just FTP main.py) Password hashing offers some additional protection in this scenario.

## Hashing a Password
If you just want to crank out some hashed user passwords, see [sha256aes.py](sha256aes.py) in this repository. You can change the username and cleartext password and then run it on your microcontroller to output a hashed password entry suitable for FTPdLite's `add_credential()`

## How It Works
The idea behind password hashing is to create a representation of the password that is easy to verify, but very difficult to reverse. This is done using a Secure Hash Algorithm (SHA). The use of a password _salt_ creates additional randomness in the password, making it less susceptible to certain kinds of attacks.

The password hashing function for FTPdLite uses SHA-256 for hashing and AES256 for salting. This is a _close, but not quite_ Unix-style password hashing, using the strongest crypto algorithms available with MicroPython and microcontroller hardware.

**While it may look similar, it is definitely not compatible with Unix-style /etc/passwd hashes.**

You can't just copy-paste from your /etc/passwd or /etc/shadow and expect things to work. They won't.

## Is It Secure?
FTP is not a secure protocol, so honestly, the question is academic. But, I think it's as secure as it can be given the available cryptography functions. Though I'm the first to admit I'm not an expert.
