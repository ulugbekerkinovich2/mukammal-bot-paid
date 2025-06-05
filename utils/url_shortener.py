# import os
# import json
# import hashlib

# SHORTENED_FILE_PATH = "shortened_urls.json"
# BASE_URL = "https://mt-call.misterdev.uz/"  # Qisqartirilgan link uchun base

# def load_data():
#     if os.path.exists(SHORTENED_FILE_PATH):
#         with open(SHORTENED_FILE_PATH, "r") as file:
#             return json.load(file)
#     return {}

# def save_data(data):
#     with open(SHORTENED_FILE_PATH, "w") as file:
#         json.dump(data, file, indent=4)

# def generate_short_code(original_url):
#     # MD5'dan 6 belgili qisqa kod
#     return hashlib.md5(original_url.encode()).hexdigest()[:6]

# def shorten_url(original_url):
#     data = load_data()

#     # Oldin qisqartirilgan bo‘lsa, mavjud kodni qaytar
#     for code, url in data.items():
#         if url == original_url:
#             return f"{BASE_URL}{code}"

#     # Yangi kod generatsiya qilish
#     short_code = generate_short_code(original_url)

#     # Ayni paytda mavjud kod bo‘lsa (kam uchraydi), boshqa kod qilish
#     while short_code in data:
#         short_code = generate_short_code(original_url + short_code)

#     # JSON'ga saqlash
#     data[short_code] = original_url
#     save_data(data)

#     return f"{BASE_URL}{short_code}"

# import pyshorteners

# s = pyshorteners.Shortener()
# print(s.tinyurl.short('https://www.youtube.com/watch?v=mrFshcqeea8'))

# import urlexpander
# urlexpander.expand('https://trib.al/xXI5ruM')