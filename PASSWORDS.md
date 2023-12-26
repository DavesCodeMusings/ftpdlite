# User Passwords
FTPdLite gives you the option of no passwords, cleartext passwords, or hashed passwords. For more about user account setup, see [ADMINISTRATION.md](ADMINISTRATION.md)

When it comes to passwords, cleartext is the most straightforward, but least secure. Cleartext passwords are visible to anyone who can view _main.py_ and this includes all users with an account. (Hint: they can just FTP get main.py)

Password hashing offers some additional protection.

## Hashing a Password
FTPdLite offers a password hashing algorithm that works with the cryptography and hashing functions available in the standard MicroPython libraries. For more information, see [sha256aes.py](sha256aes.py) in this repository.

The create a hashed password suitable for FTPdLite's add_account() method, you can use the `site hashpass` command on any running FTPdLite installation. See the example below.

```
ftp> site hashpass
501 Usage: hashpass <cleartext password>
ftp> site hashpass P@ssw0rd
211 $5a$8tgEo74S.YSY2H8r$xYHt5Y40cNQ398Ylw+PuYqx+28HXdPj8dIns389+guQ=
```
_Figure 1: Hashing a password using site hashpass_

>Note: the 211 is an FTP response code and is not part of the password.

## How It Works
The idea behind password hashing is to create a representation of the password that is easy to verify, but very difficult to reverse engineer. This is done using a Secure Hash Algorithm (SHA). The use of a password _salt_ creates additional randomness in the password, making it less susceptible to certain kinds of attacks.

The password hashing function for FTPdLite uses SHA-256 for hashing and AES256 for salting. This is a _close, but not quite_ approximation of Unix-style password hashing, using the strongest crypto algorithms available with MicroPython standard libraries.

**While it may look similar, it is definitely not compatible with Unix-style /etc/passwd hashes.**

You can't just copy-paste from your /etc/passwd or /etc/shadow and expect things to work. They won't.

## Is It Secure?
FTP is not a secure protocol, so honestly, the question is academic. But, I think it's as secure as it can be given the available cryptography functions. Though I'm the first to admit I'm not an expert.
