
import os
import base64
import hashlib
from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes

# From medium.com https://medium.com/@bh03051999/aes-gcm-encryption-and-decryption-for-python-java-and-typescript-562dcaa96c22

HASH_NAME = "SHA512"
IV_LENGTH = 12
ITERATION_COUNT = 65535
KEY_LENGTH = 32
SALT_LENGTH = 16
TAG_LENGTH = 16

KEY_ENV_VAR = "APP_ENCRYPTION_KEY"
PREFIX = "enc:v1:"

def get_secret_key(password, salt):
    return hashlib.pbkdf2_hmac(
        HASH_NAME, password.encode(), salt, ITERATION_COUNT, KEY_LENGTH
    )

def encrypt(password, plain_message):
    salt = get_random_bytes(SALT_LENGTH) 
    iv = get_random_bytes(IV_LENGTH)

    secret = get_secret_key(password, salt)

    cipher = AES.new(secret, AES.MODE_GCM, iv)

    encrypted_message_byte, tag = cipher.encrypt_and_digest(
        plain_message.encode("utf-8")
    )
    cipher_byte = salt + iv + encrypted_message_byte + tag

    encoded_cipher_byte = base64.b64encode(cipher_byte)
    return bytes.decode(encoded_cipher_byte)


def decrypt(password, cipher_message):
    decoded_cipher_byte = base64.b64decode(cipher_message)

    salt = decoded_cipher_byte[:SALT_LENGTH]
    iv = decoded_cipher_byte[SALT_LENGTH : (SALT_LENGTH + IV_LENGTH)]
    encrypted_message_byte = decoded_cipher_byte[
        (IV_LENGTH + SALT_LENGTH) : -TAG_LENGTH
    ]
    tag = decoded_cipher_byte[-TAG_LENGTH:]
    secret = get_secret_key(password, salt)
    cipher = AES.new(secret, AES.MODE_GCM, iv)

    decrypted_message_byte = cipher.decrypt_and_verify(encrypted_message_byte, tag)
    return decrypted_message_byte.decode("utf-8")

# Integration Wrappers

def get_app_encryption_key() -> str:
    key = os.environ.get(KEY_ENV_VAR)
    if not key:
        raise ValueError(f"Missing {KEY_ENV_VAR} in environment")
    return key

def encrypt_value(plaintext: str) -> str:
    """Wrapper that adds usage prefix and calls user's encrypt."""
    if not plaintext:
        return plaintext
    
    password = get_app_encryption_key()
    ciphertext = encrypt(password, plaintext)
    return f"{PREFIX}{ciphertext}"

def decrypt_value(enc_val: str) -> str:
    """Wrapper that checks prefix and calls user's decrypt."""
    
    if not enc_val or not isinstance(enc_val, str) or not enc_val.startswith(PREFIX):
        return enc_val
        
    password = get_app_encryption_key()
    raw_ciphertext = enc_val[len(PREFIX):]
    return decrypt(password, raw_ciphertext)

def encrypt_secrets(config: dict) -> dict:
    """Recursively encrypts fields in 'secrets' dictionaries."""

    if not isinstance(config, dict):
        return config  
    new_config = {}
    for k, v in config.items():
        if k in ["secrets", "secret"] and isinstance(v, dict):
            new_config[k] = {sk: encrypt_value(sv) for sk, sv in v.items() if isinstance(sv, str)}
        elif isinstance(v, dict):
            new_config[k] = encrypt_secrets(v)
        else:
            new_config[k] = v
            
    return new_config

def decrypt_secrets(config: dict) -> dict:
    """Recursively decrypts fields starting with enc:v1:."""
    
    if not isinstance(config, dict):
        return config    
    new_config = {}
    for k, v in config.items():
        if isinstance(v, str) and v.startswith(PREFIX):
             new_config[k] = decrypt_value(v)
        elif isinstance(v, dict):
            new_config[k] = decrypt_secrets(v)
        else:
            new_config[k] = v
            
    return new_config
