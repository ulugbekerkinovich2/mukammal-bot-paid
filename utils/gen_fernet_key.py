# utils/gen_fernet_key.py
from cryptography.fernet import Fernet

key = Fernet.generate_key()  # bu 32 bayt base64 URL-safe bo'ladi
with open("secret.key", "wb") as f:
    f.write(key)

print("Kalit yaratildi:", key)
