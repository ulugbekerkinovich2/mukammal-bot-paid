import logging
from typing import Dict, Any, Optional
import os
import asyncio
import random
import aiohttp
import psycopg2
from dotenv import load_dotenv
from data.config import SECRET_KEY, BASE_URL
from urllib.parse import quote  # (qolaversin, ishlatsang kerak bo‘ladi)

load_dotenv()

logger = logging.getLogger(__name__)

# =========================
# CONFIG (ENDPOINTS)
# =========================
MAIN_URL = os.getenv("REGISTER_URL", "https://dtm-api.misterdev.uz/api/v1/auth/register").strip()
BASE_API_URL = os.getenv("BASE_URL", "https://dtm-api.misterdev.uz/api/v1").strip()

ADS_BOTS = os.getenv("ADS_BOTS", "https://ads.misterdev.uz/bots/get").strip()
ADS_USERS = os.getenv("ADS_USERS", "https://ads.misterdev.uz/users/get").strip()
ADS_USERS_POST = os.getenv("ADS_USERS_POST", "https://ads.misterdev.uz/users/post").strip()
ADS_USERS_PUT = os.getenv("ADS_USERS_PUT", "https://ads.misterdev.uz/users/put/{id}").strip()
DTM_READ_URL = os.getenv("DTM_READ_URL", "https://dtm-api.misterdev.uz/api/v1/dtm/read").strip()

# =========================
# TIMEOUT PROFILES
# =========================
# Register backend sekin bo‘lishi mumkin: 180-300s
REGISTER_TIMEOUT_SEC = int(os.getenv("REGISTER_TIMEOUT_SEC", "300"))   # 5 min default
REGISTER_CONNECT_SEC = int(os.getenv("REGISTER_CONNECT_SEC", "30"))
REGISTER_RETRIES = int(os.getenv("REGISTER_RETRIES", "2"))
REGISTER_RETRY_TIMEOUT_SEC = int(os.getenv("REGISTER_RETRY_TIMEOUT_SEC", "480"))
REGISTER_RETRY_CONNECT_SEC = int(os.getenv("REGISTER_RETRY_CONNECT_SEC", "45"))
REGISTER_RETRY_ATTEMPTS = int(os.getenv("REGISTER_RETRY_ATTEMPTS", "4"))

# Oddiy GET/ADS lar uchun kichik timeout
DEFAULT_TIMEOUT_SEC = int(os.getenv("DEFAULT_TIMEOUT_SEC", "25"))
DEFAULT_CONNECT_SEC = int(os.getenv("DEFAULT_CONNECT_SEC", "7"))
DEFAULT_RETRIES = int(os.getenv("DEFAULT_RETRIES", "2"))

# Retry backoff
RETRY_BASE_SLEEP = float(os.getenv("RETRY_BASE_SLEEP", "1.2"))  # sekund
RETRY_JITTER = float(os.getenv("RETRY_JITTER", "0.35"))         # random qo‘shimcha


# =========================
# COMMON HTTP
# =========================
def _make_timeout(total: int, connect: int) -> aiohttp.ClientTimeout:
    """
    aiohttp timeoutlar:
      - total: umumiy limit
      - connect: TCP connect uchun
      - sock_connect: socket connect uchun
      - sock_read: server javob oqimini o‘qish uchun (eng muhim)
    """
    return aiohttp.ClientTimeout(
        total=total,
        connect=connect,
        sock_connect=connect,
        sock_read=total,
    )


async def _request_json(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_total: int = DEFAULT_TIMEOUT_SEC,
    timeout_connect: int = DEFAULT_CONNECT_SEC,
    retries: int = DEFAULT_RETRIES,
) -> Dict[str, Any]:
    timeout = _make_timeout(timeout_total, timeout_connect)
    last_err = ""

    for attempt in range(retries + 1):
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

                    # JSON parse
                    try:
                        data = await r.json()
                    except Exception:
                        data = None

                    # HTTP error
                    if r.status >= 400:
                        return {"ok": False, "status": r.status, "text": text, "data": data}

                    # OK
                    if isinstance(data, dict):
                        data.setdefault("ok", True)
                        data.setdefault("status", r.status)
                        return data

                    return {"ok": True, "status": r.status, "data": data, "text": text}

        except asyncio.TimeoutError as e:
            last_err = f"TimeoutError(): {repr(e)}"
        except aiohttp.ClientError as e:
            last_err = f"ClientError(): {repr(e)}"
        except Exception as e:
            last_err = f"Exception(): {repr(e)}"

        # retry sleep (backoff + jitter)
        if attempt < retries:
            backoff = RETRY_BASE_SLEEP * (attempt + 1)
            jitter = random.random() * RETRY_JITTER
            await asyncio.sleep(backoff + jitter)

    return {"ok": False, "status": 0, "text": f"Network error after retries: {last_err}", "data": None}


# =========================
# REGISTER
# =========================
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
    status: bool = True,
    test_type: str = "offline",
) -> Dict[str, Any]:
    return {
        "bot_id": str(bot_id),
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
        "status": status,
        "test_type": test_type,
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
    retries: int = REGISTER_RETRIES,
    status: bool = True,
    test_type: str = "offline",
    timeout_total: Optional[int] = None,
    timeout_connect: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Register uchun timeout katta:
      - total: REGISTER_TIMEOUT_SEC (default 300s)
      - connect: REGISTER_CONNECT_SEC (default 30s)
      - sock_read: total bilan teng (server sekin javob bersa ham kutadi)
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
        group_name=group_name,
        status=status,
        test_type=test_type,
    )

    timeout_total = int(timeout_total or REGISTER_TIMEOUT_SEC)
    timeout_connect = int(timeout_connect or REGISTER_CONNECT_SEC)

    logger.info(
        f"\n\n========== REGISTER REQUEST ==========\n"
        f"URL: {MAIN_URL}\n"
        f"PAYLOAD: {payload}\n"
        f"TIMEOUT: {timeout_total} CONNECT: {timeout_connect} RETRIES: {retries}\n"
        f"======================================\n"
    )

    res = await _request_json(
        "POST",
        MAIN_URL,
        json_data=payload,
        headers={"Content-Type": "application/json"},
        retries=retries,
        timeout_total=timeout_total,
        timeout_connect=timeout_connect,
    )

    logger.info(
        f"\n\n========== REGISTER RESPONSE ==========\n"
        f"RESPONSE: {res}\n"
        f"=======================================\n"
    )

    return res


# =========================
# ADS
# =========================
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


# =========================
# DB (sync psycopg2)
# =========================
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


def get_user_file_url(chat_id):
    """
    Userning oxirgi file_url sini bazadan olib beradi.
    """
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
                    SELECT file_url FROM users
                    WHERE chat_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (str(chat_id),),
                )
                row = cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        print(f"DATABASE GET_FILE_URL ERROR => {e}")
        return None
    finally:
        conn.close()


# =========================
# global.misterdev.uz (unchanged)
# =========================
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


# =========================
# Management endpoints (BASE_URL + SECRET_KEY)
# =========================
def _build_url(path: str) -> str:
    """
    BASE_URL qaysi ko‘rinishda bo‘lishidan qat'i nazar, urlni to‘g‘ri yig‘adi.
    """
    base = (BASE_URL or "").rstrip("/")
    p = (path or "").lstrip("/")

    # BASE_URL /api/v1 bilan tugasa, dubl bo‘lib ketmasin
    if base.endswith("/api/v1") and p.startswith("api/v1/"):
        p = p[len("api/v1/"):]
    if base.endswith("/api") and p.startswith("api/"):
        p = p[len("api/"):]
    return f"{base}/{p}"


def _auth_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {"accept": "application/json"}
    api_key = (SECRET_KEY or "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    if extra:
        headers.update(extra)
    return headers


async def fetch_districts():
    url = _build_url("/api/v1/management/districts")
    return await _request_json("GET", url, headers=_auth_headers(), timeout_total=DEFAULT_TIMEOUT_SEC, timeout_connect=DEFAULT_CONNECT_SEC)


async def fetch_district_by_id(district_id: int):
    url = _build_url(f"/api/v1/management/districts/{district_id}")
    return await _request_json("GET", url, headers=_auth_headers(), timeout_total=DEFAULT_TIMEOUT_SEC, timeout_connect=DEFAULT_CONNECT_SEC)


async def fetch_schools():
    url = _build_url("/api/v1/management/schools")
    return await _request_json("GET", url, headers=_auth_headers(), timeout_total=DEFAULT_TIMEOUT_SEC, timeout_connect=DEFAULT_CONNECT_SEC)


async def fetch_school_by_id(school_id: int):
    url = _build_url(f"/api/v1/management/schools/{school_id}")
    return await _request_json("GET", url, headers=_auth_headers(), timeout_total=DEFAULT_TIMEOUT_SEC, timeout_connect=DEFAULT_CONNECT_SEC)


def _detect_image_content_type(image_bytes: bytes, fallback: str = "image/jpeg") -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return fallback or "image/jpeg"


def _normalize_image_filename(filename: str, content_type: str) -> str:
    name = (filename or "sheet").strip() or "sheet"
    lower_name = name.lower()
    if content_type == "image/png" and not lower_name.endswith(".png"):
        return f"{name}.png"
    if content_type == "image/jpeg" and not (lower_name.endswith(".jpg") or lower_name.endswith(".jpeg")):
        return f"{name}.jpg"
    return name


async def submit_dtm_read(image_bytes: bytes, filename: str, book_id: str, content_type: str = "image/jpeg") -> Dict[str, Any]:
    actual_content_type = _detect_image_content_type(image_bytes, content_type)
    actual_filename = _normalize_image_filename(filename, actual_content_type)
    timeout = _make_timeout(REGISTER_TIMEOUT_SEC, REGISTER_CONNECT_SEC)
    form = aiohttp.FormData()
    form.add_field(
        "file",
        image_bytes,
        filename=actual_filename,
        content_type=actual_content_type,
    )
    form.add_field("book_id", str(book_id))

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(DTM_READ_URL, data=form, headers=_auth_headers()) as r:
                text = await r.text()
                try:
                    data = await r.json()
                except Exception:
                    data = None

                if r.status >= 400:
                    return {"ok": False, "status": r.status, "text": text, "data": data}

                return {
                    "ok": True,
                    "status": r.status,
                    "data": data,
                    "text": text,
                }
    except asyncio.TimeoutError as e:
        return {"ok": False, "status": 0, "text": f"TimeoutError(): {repr(e)}", "data": None}
    except aiohttp.ClientError as e:
        return {"ok": False, "status": 0, "text": f"ClientError(): {repr(e)}", "data": None}
    except Exception as e:
        return {"ok": False, "status": 0, "text": f"Exception(): {repr(e)}", "data": None}


async def get_dtm_result(document_code):
    """
    Yangi API orqali natijani olib beradi.
    GET /api/v1/dtm/result/{document_code}
    """
    from data.config import BASE_URL
    import os
    import aiohttp
    
    secret_key = os.getenv("SECRET_KEY", "K0yKC4LYBnCNLncjE5BH57i13yZIBhaT")
    url = f"{BASE_URL}/dtm/result/by_chat/{document_code}"
    headers = {
        "x-api-key": secret_key,
        "accept": "application/json"
    }
    
    logger.info(
        f"\n\n========== RESULT REQUEST ==========\n"
        f"CHAT_ID: {document_code}\n"
        f"URL: {url}\n"
        f"====================================\n"
    )
    
    res = await _request_json("GET", url, headers=headers)
    
    logger.info(
        f"\n\n========== RESULT RESPONSE ==========\n"
        f"RESPONSE: {res}\n"
        f"=====================================\n"
    )
    return res


def check_user_exists(chat_id):
    """
    User bazada borligini tekshiradi (har qanday test_type bilan).
    """
    import os
    import psycopg2
    db_name = os.getenv("db_name")
    if db_name:
        db_name = db_name.strip('"')

    try:
        conn = psycopg2.connect(
            host=os.getenv("db_host"),
            database=db_name,
            user=os.getenv("db_user"),
            password=os.getenv("db_pass"),
            port=os.getenv("db_port"),
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE chat_id = %s LIMIT 1", (str(chat_id),))
                return cur.fetchone() is not None
    except Exception as e:
        print(f"DATABASE CHECK_USER ERROR => {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            conn.close()


def check_user_exists_by_type(chat_id, test_type: str = "offline"):
    """
    User bazada (chat_id, test_type) juftligi bilan borligini tekshiradi.
    True = registratsiya bor, False = registratsiya yo'q (yoki DB xato).
    """
    import os
    import psycopg2
    db_name = os.getenv("db_name")
    if db_name:
        db_name = db_name.strip('"')

    try:
        conn = psycopg2.connect(
            host=os.getenv("db_host"),
            database=db_name,
            user=os.getenv("db_user"),
            password=os.getenv("db_pass"),
            port=os.getenv("db_port"),
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM users WHERE chat_id = %s AND test_type = %s LIMIT 1",
                    (str(chat_id), test_type),
                )
                return cur.fetchone() is not None
    except Exception as e:
        print(f"DATABASE CHECK_USER_BY_TYPE ERROR => {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            conn.close()
