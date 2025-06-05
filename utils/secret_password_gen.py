# encryptor.py
from cryptography.fernet import Fernet

# Kalitni fayldan o‘qish
with open("secret.key", "rb") as key_file:
    key = key_file.read()

cipher = Fernet(key)

# Parol
password = "Mentalaba123!"

# 🔐 Shifrlash
encrypted = cipher.encrypt(password.encode())
print(f"Shifrlangan parol: {encrypted}")

# 🔓 Ochish
decrypted = cipher.decrypt(encrypted).decode()
print(f"Ochilgan parol: {decrypted}")
