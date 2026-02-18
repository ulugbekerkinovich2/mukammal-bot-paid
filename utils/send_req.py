from typing import Dict, Any, Optional
import os
import asyncio
import aiohttp
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ====== CONFIG ======
MAIN_URL = "https://dtmpaperreaderapi.mentalaba.uz/api/v1/auth/register"
BASE_URL = "https://dtmpaperreaderapi.mentalaba.uz/api/v1"

ADS_BOTS = "https://ads.misterdev.uz/bots/get"
ADS_USERS = "https://ads.misterdev.uz/users/get"
ADS_USERS_POST = "https://ads.misterdev.uz/users/post"
ADS_USERS_PUT = "https://ads.misterdev.uz/users/put/{id}"


# ====== COMMON HTTP ======
async def _request_json(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_total: int = 25,
    timeout_connect: int = 7,
    retries: int = 2,
) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=timeout_total, connect=timeout_connect)
    last_err = ""

    for _ in range(retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method.upper(),
                    url,
                    params=params,
                    json=json_data,
                    headers=headers,
                ) as r:
                    text = await r.text()
                    try:
                        data = await r.json()
                    except Exception:
                        data = None

                    if r.status >= 400:
                        return {"ok": False, "status": r.status, "text": text, "data": data}

                    if isinstance(data, dict):
                        data.setdefault("ok", True)
                        data.setdefault("status", r.status)
                        return data

                    return {"ok": True, "status": r.status, "data": data, "text": text}

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_err = repr(e)

    return {"ok": False, "status": 0, "text": f"Network error after retries: {last_err}", "data": None}


# ====== REGISTER (NO QUEUE) ======
class RegisterError(Exception):
    pass


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
    group_name: str,
) -> Dict[str, Any]:
    return {
        "bot_id": str(bot_id),  # ⚠️ bu yerda endi HARD-CODE YO‘Q
        "full_name": full_name,
        "phone": phone,
        "school_code": school_code,
        "first_subject_id": int(first_subject_id),
        "second_subject_id": int(second_subject_id),
        "password": password,
        "role": "user",
        "language": language,
        "gender": gender,
        "district": district or "",
        "region": region or "",
        "group_name": group_name or "",
    }


async def register_user(
    bot_id: str,
    full_name: str,
    phone: str,
    school_code: str,
    first_subject_id: int,
    second_subject_id: int,
    password: str = "1111",
    language: str = "uz",
    gender: str = "male",
    district: str = "",
    region: str = "",
    group_name: str = "",
    retries: int = 2,
) -> Dict[str, Any]:

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
        group_name=group_name,
    )

    print("\n========== REGISTER REQUEST ==========")
    print("URL:", MAIN_URL)
    print("PAYLOAD:", payload)
    print("======================================\n")

    res = await _request_json(
        "POST",
        MAIN_URL,
        json_data=payload,
        headers={"Content-Type": "application/json"},
        retries=retries,
    )

    print("\n========== REGISTER RESPONSE ==========")
    print("RESPONSE:", res)
    print("=======================================\n")

    return res



# ====== ADS (NO HttpClient, NO Queue) ======
async def get_all_bots() -> Dict[str, Any]:
    return await _request_json("GET", ADS_BOTS)


async def get_all_users(bot_id_filter: str = "7") -> Dict[str, Any]:
    res = await _request_json("GET", ADS_USERS)
    if not res.get("ok"):
        return res

    data = res.get("data") or []
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
    return await _request_json("POST", ADS_USERS_POST, json_data=payload)


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
    return await _request_json("PUT", url, json_data=payload)


# ====== DB (sync psycopg2) ======
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


# ====== global.misterdev.uz (unchanged) ======
async def get_user(user_chat_id, uni_id):
    url = f"https://global.misterdev.uz/detail-user-profile/{user_chat_id}/{uni_id}/"
    return await _request_json("GET", url)


async def add_chat_id(chat_id_user, first_name_user, last_name_user, pin, phone, username, date):
    url = "https://global.misterdev.uz/create-user-profile/"
    payload = {
        "chat_id_user": chat_id_user,
        "first_name_user": first_name_user,
        "last_name_user": last_name_user,
        "pin": pin,
        "phone": phone,
        "username": username,
        "date": date,
        "university_name": 5,
    }
    return await _request_json("POST", url, json_data=payload)


# ====== Your existing fetch_* (kept, but cleaned to use _request_json) ======
async def fetch_school_and_districts(region: str, district: str):
    url = f"{BASE_URL}/admin/districts-and-schools"
    return await _request_json("GET", url, params={"region": region, "district": district})


async def fetch_districts():
    url = f"{BASE_URL}/management/districts"
    headers = {"Content-Type": "application/json", "x-api-key": os.getenv("SECRET_KEY", "")}
    return await _request_json("GET", url, headers=headers, timeout_total=20, timeout_connect=7)


async def fetch_district_by_id(district_id: int):
    url = f"{BASE_URL}/management/districts/{district_id}"
    headers = {"Content-Type": "application/json", "x-api-key": os.getenv("SECRET_KEY", "")}
    return await _request_json("GET", url, headers=headers, timeout_total=20, timeout_connect=7)


async def fetch_schools():
    url = f"{BASE_URL}/management/schools"
    headers = {"Content-Type": "application/json", "x-api-key": os.getenv("SECRET_KEY", "")}
    return await _request_json("GET", url, headers=headers, timeout_total=20, timeout_connect=7)


async def fetch_school_by_id(school_id: int):
    url = f"{BASE_URL}/management/schools/{school_id}"
    headers = {"Content-Type": "application/json", "x-api-key": os.getenv("SECRET_KEY", "")}
    return await _request_json("GET", url, headers=headers, timeout_total=20, timeout_connect=7)
