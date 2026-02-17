from typing import Dict, Any, Optional
import aiohttp
import os
from dotenv import load_dotenv
import psycopg2

from utils.http_client import HttpClient
from utils.job_queue import JobQueue

load_dotenv()

MAIN_URL = "https://dtm-api.misterdev.uz/api/v1/auth/register"
BASE_URL = "https://dtm-api.misterdev.uz/api/v1"
# Global singletonlar (bot ishga tushganda start qilasiz)
http = HttpClient(max_concurrency=20, timeout_total=30, timeout_connect=5, retry=3)
queue = JobQueue(workers=10, maxsize=2000)


class RegisterError(Exception):
    pass


async def startup():
    """Bot start bo'lganda chaqiring."""
    await http.start()
    await queue.start()


async def shutdown():
    """Bot stop bo'lganda chaqiring."""
    await queue.stop()
    await http.close()


def _register_payload(
    bot_id: str,
    full_name: str,
    phone: str,
    school_code: str,
    first_subject_id: int,
    second_subject_id: int,
    password: str,
    language: str,
    gender: str,
    district: str,
    region: str,
    group_name: str
) -> Dict[str, Any]:
    return {
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
        "district": district,
        "region": region,
        "group_name": group_name
    }


async def register_job(
    bot_id: str,
    full_name: str,
    phone: str,
    school_code: str,
    first_subject_id: int,
    second_subject_id: int,
    password: str,
    language: str,
    gender: str,
    district: str,
    region: str,
    group_name: str
) -> Dict[str, Any]:
    """
    Bu FUNKSIYA bot handler ichida chaqiriladi.
    U requestni queue ga qo'yadi, workerlar bajaradi.
    """
    payload = _register_payload(
        bot_id=bot_id,
        full_name=full_name,
        phone=phone,
        school_code=school_code,
        first_subject_id=first_subject_id,
        second_subject_id=second_subject_id,
        password=password,
        language=language,
        gender=gender,
        district=district,
        region=region,
        group_name=group_name
    )

    async def do_call():
        res = await http.request_json(
            "POST",
            MAIN_URL,
            json_data=payload,
            headers={"Content-Type": "application/json"},
        )
        return res

    try:
        return await queue.submit(do_call)
    except Exception as e:
        raise RegisterError(f"❌ Network/Server xato: {e}")


# ---- ADS endpoints (xohlasangiz bularni ham queue orqali yuboramiz) ----

ADS_BOTS = "https://ads.misterdev.uz/bots/get"
ADS_USERS = "https://ads.misterdev.uz/users/get"
ADS_USERS_POST = "https://ads.misterdev.uz/users/post"
ADS_USERS_PUT = "https://ads.misterdev.uz/users/put/{id}"


async def get_all_bots() -> Dict[str, Any]:
    return await http.request_json("GET", ADS_BOTS)


async def get_all_users(bot_id_filter: str = "7") -> Dict[str, Any]:
    res = await http.request_json("GET", ADS_USERS)
    if not res.get("ok"):
        return res

    data = res["data"]
    filtered = [i for i in data if str(i.get("bot_id")) == str(bot_id_filter)]
    return {"ok": True, "status": 200, "data": filtered}


async def save_chat_id(chat_id, firstname, lastname, bot_id, username, status):
    payload = {
        "chat_id": chat_id,
        "firstname": firstname or "firstname not found",
        "lastname": lastname or "lastname not found",
        "bot_id": bot_id,
        "username": username or "username not found",
        "status": status,
    }
    return await http.request_json("POST", ADS_USERS_POST, json_data=payload)


async def update_user(id, chat_id, firstname, lastname, bot_id, username, status, created_at):
    url = ADS_USERS_PUT.format(id=id)
    payload = {
        "chat_id": chat_id,
        "firstname": firstname or "firstname not found",
        "lastname": lastname or "lastname not found",
        "bot_id": bot_id,
        "username": username or "username not found",
        "status": status,
        "created_at": created_at,
    }
    return await http.request_json("PUT", url, json_data=payload)


# ---- DB: sync psycopg2 (keyin asyncpg qilamiz) ----
def update_user_status(chat_id, bot_id, status="blocked"):
    conn = psycopg2.connect(
        host=os.getenv("db_host"),
        database=os.getenv("db_name"),
        user=os.getenv("db_user"),
        password=os.getenv("db_pass"),
        port=os.getenv("db_port"),
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
                    (status, chat_id, bot_id),
                )
                return cur.rowcount
    finally:
        conn.close()


# ---- Sizdagi global.misterdev.uz async funksiyalar qoladi ----
async def get_user(user_chat_id, uni_id):
    url = f"https://global.misterdev.uz/detail-user-profile/{user_chat_id}/{uni_id}/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 404:
                return None
            response.raise_for_status()
            return await response.json()


async def add_chat_id(chat_id_user, first_name_user, last_name_user, pin, phone, username, date):
    url = "https://global.misterdev.uz/create-user-profile/"
    data = {
        "chat_id_user": chat_id_user,
        "first_name_user": first_name_user,
        "last_name_user": last_name_user,
        "pin": pin,
        "phone": phone,
        "username": username,
        "date": date,
        "university_name": 5,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            text = await response.text()
            if response.status >= 400:
                return {"ok": False, "status": response.status, "text": text}
            return await response.json()


async def fetch_school_and_districts(region: str, district: str):
    url = f"{BASE_URL}/admin/districts-and-schools"

    params = {"region": region, "district": district}

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            # avval text o‘qib olamiz (xatolik bo‘lsa ko‘rsatish uchun)
            text = await response.text()

            if response.status >= 400:
                return {"ok": False, "status": response.status, "text": text}


            try:
                data = await response.json()
            except aiohttp.ContentTypeError:
                return {"ok": False, "status": response.status, "text": text}

            return data