import aiohttp
from data.config import main_url
from icecream import ic
import requests
import json
async def auth_check(phone):
    url = f"{main_url}/v1/auth/check"
    payload = {
        "phone": phone
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            return await response.text()


import aiohttp

async def user_register(phone, password):
    url = f"{main_url}/v2/auth/register"
    payload = {
        "phone": phone,
        "password": password
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            content_type = response.headers.get("Content-Type", "")

            if "application/json" in content_type:
                data = await response.json()
            else:
                text = await response.text()
                data = {
                    "error": "Unexpected content type",
                    "content_type": content_type,
                    "raw_response": text
                }

            return data, status_


async def user_verify(phone, code):
    url = f"{main_url}/v2/auth/verify"
    payload = {
        "code": code,
        "phone": phone
    }
    headers = {
        "Content-Type": "application/json"
    }
    # print(payload)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
    
async def user_info(birth_date, document, token):
    url = f"{main_url}/v1/info"
    
    payload = {
        "birth_date": birth_date,
        "browser_name": "Telegram",
        "device_name": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "document": document,
        "ip_address": "45.150.24.19"
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Referer": "https://mentalaba.uz/",
        "Origin": "https://mentalaba.uz"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            content_type = response.headers.get("Content-Type", "")
            
            # Agar JSON bo'lsa qaytaramiz
            if "application/json" in content_type:
                json_data = await response.json()
                return json_data, status_
            else:
                text = await response.text()
                print(f"[Xatolik] Kutilmagan content-type: {content_type}")
                print(f"[Javob body]: {text}")
                return {"error": "Unexpected response format", "raw": text}, status_

        

async def user_login(phone, password):
    url = f"{main_url}/v1/auth/user/login"
    payload = {
        "phone": phone,
        "password": password
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
    
async def delete_user(token, phone, password):
    url = f"{main_url}/v1/users/delete-account"
    payload = {
        "phone": phone,
        "password": password
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    ic(headers, payload)

    async with aiohttp.ClientSession() as session:
        async with session.delete(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        


async def upload_image(token, image_path):
    url = f"{main_url}/v1/images/upload"

    headers = {
        "Authorization": f"Bearer {token}"
        # Content-Type'ni yozmang — aiohttp o'zi qo'shadi!
    }

    form = aiohttp.FormData()
    form.add_field("associated_with", "users")
    form.add_field("usage", "avatar")
    form.add_field(
        "file",
        open(image_path, "rb"),
        filename="avatar.png",
        content_type="image/png"
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form, headers=headers) as response:
            status_ = response.status
            response_json = await response.json()
            return response_json, status_


import aiohttp

async def upload_file(token, image_path):
    url = f"{main_url}/v1/images/upload"

    headers = {
        "Authorization": f"Bearer {token}"
        # Content-Type yozilmaydi, aiohttp FormData uchun o'zi qo'shadi
    }

    form = aiohttp.FormData()
    form.add_field("associated_with", "users")
    form.add_field("usage", "diploma")

    with open(image_path, "rb") as f:
        form.add_field(
            "file",
            f,
            filename="diploma.png"  # kerak bo'lsa dinamik o'zgartiring
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form, headers=headers) as response:
                status_ = response.status
                response_json = await response.json()
                return response_json, status_


async def fetch_regions(token):
    url = f"{main_url}/v1/locations/regions?status=active"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
    

async def fetch_educations(token):
    url =f"{main_url}/v1/education-types/educations"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
async def district_locations(id, token):
    url = f"{main_url}/v1/locations/districts/{id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
async def me(token):
    url = f"{main_url}/v1/application-form/me"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
async def update_application_form(token, district_id, region_id, institution_name, graduation_year, file_path):
    import json
    url = f"{main_url}/v1/application-form"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "update_required_section": "having_problem_with_education",
        "user_education": {
            "country_id": 234,
            "district_id": int(district_id),
            "education_type": "1",
            "file": [file_path],  # server bu joyda list kutayaptimi, aniq bilib ol
            "graduation_year": int(graduation_year),
            "institution_name": institution_name,
            "region_id": int(region_id),
            "src": "manually"
        }
    }
    ic(payload)
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, data=json.dumps(payload), headers=headers) as response:
            status_ = response.status

            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                json_data = await response.json()
            else:
                text_data = await response.text()
                print(f"[!] Unexpected Content-Type: {content_type}")
                print(f"[!] Response body: {text_data}")
                json_data = {}

            return json_data, status_
        
    
# import aiohttp
# import asyncio

async def shorten_url_async(long_url):
    # print(long_url)
    url = "https://global.misterdev.uz/shorten/"
    payload = {
        "url": str(long_url)
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            response.raise_for_status()  # xatolik bo‘lsa except blokga tushadi
            return await response.json()
        
async def add_chat_id(chat_id_user,first_name_user,last_name_user,pin,phone,username,date):
    url = "https://global.misterdev.uz/create-user-profile/"
    data = {
        "chat_id_user": chat_id_user,
        "first_name_user": first_name_user,
        "last_name_user": last_name_user,
        "pin": pin,
        "phone": phone,
        "username": username,
        "date": date,
        "university_name": 5
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            response.raise_for_status()  # xatolik bo‘lsa except blokga tushadi
            return await response.json()
        
async def get_user(user_chat_id, uni_id):
    url = f"https://global.misterdev.uz/detail-user-profile/{user_chat_id}/{uni_id}/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 404:
                return None
            else:
                response.raise_for_status()  # xatolik bo‘lsa except blokga tushadi
                return await response.json()
            # response.raise_for_status()  # xatolik bo‘lsa except blokga tushadi
            # return await response.json()

    
async def change_password(phone):
    url = f"{main_url}/v1/auth/forgot-password"
    payload = {
        "phone": phone
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            print(status_, await response.json())
            return await response.json(), status_
        
async def user_verify_by_id(id, code):
    url = f"{main_url}/v1/auth/verify"
    payload = {
        "code": int(code),
        "id": id
    }
    headers = {
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        
async def reset_password(id, password, phone):
    url = f"{main_url}/v1/auth/reset-password"
    payload = {
        "id": id,
        "password": password,
        "phone": phone
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status_ = response.status
            return await response.json(), status_
        


def get_all_bots():
    url = "https://ads.misterdev.uz/bots/get"
    response = requests.get(url)
    return response.json()

def get_all_users():
    url = "https://ads.misterdev.uz/users/get"
    response = requests.get(url)
    data = [i for i in response.json() if i['bot_id'] == 7 or i['bot_id'] == "7"]
    # response = [
    # {
    #     "id": 30927,
    #     "firstname": "Ulugbek",
    #     "lastname": "Erkinov",
    #     "chat_id": "935920479",
    #     "username": "@status_developer",
    #     "created_at": None,
    #     "status": "active",
    #     "bot_id": 7
    # },
    # {
    #     "id": 30298,
    #     "firstname": "user",
    #     "lastname": "not found",
    #     "chat_id": "5204054835",
    #     "username": "not found",
    #     "created_at": "2025-08-29 14:42:38.470762+05",
    #     "status": "active",
    #     "bot_id": 7
    # }
    # ]
    # return response
    return data

def update_user(id, chat_id,firstname, lastname,bot_id,username,status,created_at):
    url = f"https://ads.misterdev.uz/users/put/{id}"
    data = {
        "chat_id": chat_id,
        "firstname": firstname if firstname else "firstname not found",
        "lastname": lastname if lastname else "lastname not found",
        "bot_id": bot_id,
        "username": username if username else "username not found",
        "status": status,
        'created_at': created_at
        }
    ic("update",data)
    response = requests.put(url, json=data)
    return response.json()

def save_chat_id(chat_id,firstname, lastname,bot_id,username,status):
    url = "https://ads.misterdev.uz/users/post"
    data = {
        "chat_id": chat_id,
        "firstname": firstname if firstname else "firstname not found",
        "lastname": lastname if lastname else "lastname not found",
        "bot_id": bot_id,
        "username": username if username else "username not found",
        "status": status
        }
    ic(data)
    response = requests.post(url, json=data)
    
    return response.json()

import psycopg2
from dotenv import load_dotenv
import os
load_dotenv()
def update_user_status(chat_id, bot_id, status="blocked"):
    conn = psycopg2.connect(
        host=os.getenv("db_host"),
        database=os.getenv("db_name"),
        user=os.getenv("db_user"),
        password=os.getenv("db_pass"),
        port=os.getenv("db_port")
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET status = %s
                    WHERE chat_id = %s AND bot_id_id = %s
                    """,
                    (status, chat_id, bot_id)
                )
                return cur.rowcount  # necha qator update qilinganini qaytaradi
    finally:
        conn.close()
