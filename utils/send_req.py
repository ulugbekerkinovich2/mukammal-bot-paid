import requests
from typing import Dict, Any
import random
import json
import aiohttp
MAIN_URL = "https://dtm-api.misterdev.uz/api/v1/auth/register"

session = requests.Session()
session.headers.update({
    "Content-Type": "application/json",
    "Accept": "application/json",
})


class RegisterError(Exception):
    pass
random_number = random.randint(1000000, 9999999)

def register(
    bot_id: str,
    full_name: str,
    phone: str,
    school_code: str,
    first_subject_id: int,
    second_subject_id: int,
    password: str,
    language: str,
    gender: str,
    timeout: int = 60,
) -> Dict[str, Any]:

    payload = {
        "bot_id": str(bot_id),
        "full_name": full_name,
        "phone": phone,
        "school_code": school_code,
        "first_subject_id": first_subject_id,
        "second_subject_id": second_subject_id,
        "password": password,
        "role": "user",
        "language": language,
        "gender": gender,
    }


    try:
        response = session.post(MAIN_URL, json=payload, timeout=timeout)

        response.raise_for_status()

        return response

    except requests.exceptions.Timeout:
        raise RegisterError("⏱ Server javob bermadi (timeout).")

    except requests.exceptions.HTTPError:
        raise RegisterError(
            f"❌ Server xatosi ({response.status_code}): {response.text}"
        )

    except requests.exceptions.RequestException as e:
        raise RegisterError(f"❌ Network xato: {e}")




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
    # ic("update",data)
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
    # ic(data)
    response = requests.post(url, json=data)
    res = response.json()
    print(res)
    return res

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


async def get_user(user_chat_id, uni_id):
    url = f"https://global.misterdev.uz/detail-user-profile/{user_chat_id}/{uni_id}/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 404:
                return None
            else:
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
            data = await response.text()
            print(response.status, data)

            response.raise_for_status()
            return await response.json()
        
