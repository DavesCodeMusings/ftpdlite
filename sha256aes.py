# Password hashing class that works with MicroPython v1.21
# There's no SHA512 or bcrypt in MicroPython, so use SHA256 and AES.
# Close to a Unix-like system password, but not compatible.

from random import choice, seed
from cryptolib import aes
from hashlib import sha256
from binascii import b2a_base64

# Change this to suit your needs before running.
user_name = "Felicia"
user_pw = "Friday"


class SHA256AES:
    """
    Password hashing for MicroPython.
    """
    _method_token = "5a" # This is made up. Not a standard.

    @staticmethod
    def generate_salt(length):
        """
        Generate a random-character salt suitable for password hashing.
        """
        valid_chars = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        seed()
        salt = ""
        for i in range(length):
            salt += choice(valid_chars)
        return salt

    @staticmethod
    def create_salted_hash(salt, cleartext):
        """
        Given a salt value and password in cleartext, return a hashed password.
        """
        assert(len(salt) % 16 == 0)
        cleartext = bytes(cleartext, "utf8")
        cleartext += bytearray(16 - (len(cleartext) % 16))  # Pad out to 16-byte boundry
        cipher = aes(salt, 1)  # 1 is MODE_ECB, the only one supported by MicroPython
        salted_pw = cipher.encrypt(cleartext)
        return b2a_base64(sha256(salted_pw).digest()).decode('utf8').rstrip('\n')

    @staticmethod
    def create_passwd_entry(cleartext):
        salt = SHA256AES.generate_salt(16) # Must be evenly divisible by 16 for AES
        hashed_pw = SHA256AES.create_salted_hash(salt, cleartext)
        return f"${SHA256AES._method_token}${salt}${hashed_pw}"

    @staticmethod
    def verify_passwd_entry(hashed, cleartext):
        """
        Given a hashed password, verify the cleartext password is valid.
        """
        if hashed.count("$") != 3:
            print("Invalid hashed password format.")
            return False
        else:
            _, hash_alg, salt, hashed_pw = hashed.split("$")
            if hash_alg != SHA256AES._method_token:
                print("Unsupported hash algorithm.")
            else:
                rehashed_pw = SHA256AES.create_salted_hash(salt, cleartext)
                if hashed_pw != rehashed_pw:
                    return False
                else:
                    return True


# Hash the password for the user.
passwd_entry = SHA256AES.create_passwd_entry(user_pw)
print(f"Credential entry is...\n{user_name}:{passwd_entry}")
