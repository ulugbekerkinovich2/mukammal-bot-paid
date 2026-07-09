import logging
from typing import Dict, Any, Optional, Iterable
import os
import asyncio
import random
import aiohttp
import psycopg2
from dotenv import load_dotenv
from data.config import SECRET_KEY, BASE_URL, BASE_URL_2, ADMIN_API_BASE, ADMIN_TOKEN, BOT_DB_ID, BOT_TOKEN
from urllib.parse import quote  # (qolaversin, ishlatsang kerak bo‘ladi)

load_dotenv()

logger = logging.getLogger(__name__)


# =========================
# TEST TYPE
# =========================
VALID_TEST_TYPES = ("offline", "online")
DEFAULT_TEST_TYPE = "offline"


def normalize_test_type(value: Any) -> str:
    """
    Backend semantics (see API doc):
      - NULL / missing / unknown → "offline"
      - case-insensitive, surrounding whitespace ignored
    Returns one of VALID_TEST_TYPES.
    """
    if value is None:
        return DEFAULT_TEST_TYPE
    s = str(value).strip().lower()
    if s in VALID_TEST_TYPES:
        return s
    return DEFAULT_TEST_TYPE


def extract_test_type(obj: Any) -> str:
    """Pull test_type out of a user-shaped dict; defaults to 'offline'."""
    if isinstance(obj, dict):
        return normalize_test_type(obj.get("test_type"))
    return DEFAULT_TEST_TYPE

# =========================
# CONFIG (ENDPOINTS)
# =========================
MAIN_URL = os.getenv("REGISTER_URL", "https://dtm-api.misterdev.uz/api/v1/auth/register").strip()
BASE_API_URL = os.getenv("BASE_URL", "https://dtm-api.misterdev.uz/api/v1").strip()

# =========================
# LOAD BALANCER (round-robin + failover)
# =========================
_LB_BACKENDS: list = [
    u.rstrip("/") for u in [BASE_URL, BASE_URL_2] if u and u.strip()
]
_lb_counter: int = 0


def _next_backend() -> str:
    global _lb_counter
    if not _LB_BACKENDS:
        return BASE_API_URL
    url = _LB_BACKENDS[_lb_counter % len(_LB_BACKENDS)]
    _lb_counter += 1
    return url


async def _request_json_lb(
    method: str,
    path: str,
    **kwargs,
) -> Dict[str, Any]:
    """Round-robin + failover. path = "/dtm/online/v2/complete" kabi.
    Birinchi backend ishlamasa avtomatik ikkinchisiga o'tadi."""
    global _lb_counter
    backends = _LB_BACKENDS if _LB_BACKENDS else [BASE_API_URL]
    start = _lb_counter % len(backends)
    last_res: Dict[str, Any] = {}
    for i in range(len(backends)):
        base = backends[(start + i) % len(backends)]
        url = base.rstrip("/") + "/" + path.lstrip("/")
        res = await _request_json(method, url, **kwargs)
        status = res.get("status", 0)
        # 0 = network error (server down), 5xx = server error → keyingisiga o't
        # 2xx yoki 4xx (client error) → qaytaramiz
        if res.get("ok") or (0 < status < 500):
            _lb_counter = start + i + 1
            return res
        last_res = res
        logger.warning("[lb] backend %s failed status=%s, trying next", base, status)
    return last_res

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
    test_type: str = DEFAULT_TEST_TYPE,
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
        "test_type": normalize_test_type(test_type),
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
    test_type: str = DEFAULT_TEST_TYPE,
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
        test_type=normalize_test_type(test_type),
    )

    timeout_total = int(timeout_total or REGISTER_TIMEOUT_SEC)
    timeout_connect = int(timeout_connect or REGISTER_CONNECT_SEC)

    logger.info(f"[register] request phone={payload.get('phone')} school_code={payload.get('school_code')} test_type={payload.get('test_type')} timeout={timeout_total} connect={timeout_connect} retries={retries}")

    res = await _request_json_lb(
        "POST",
        "/auth/register",
        json_data=payload,
        headers={"Content-Type": "application/json"},
        retries=retries,
        timeout_total=timeout_total,
        timeout_connect=timeout_connect,
    )

    logger.info(f"[register] response ok={res.get('ok')} status={res.get('status')}" + (f" text={str(res.get('text',''))[:100]}" if not res.get('ok') else ""))

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


# =========================
# /me, /dtm/users, /dtm/user/{id}, /auth/pending-bot-id-registrations
# Backend yangi `test_type` filtri va response maydonini qo'llab-quvvatlaydi.
# =========================
def _with_test_type_param(
    params: Optional[Dict[str, Any]],
    test_type: Optional[str],
) -> Optional[Dict[str, Any]]:
    if test_type is None:
        return params
    normalized = normalize_test_type(test_type)
    out = dict(params or {})
    out["test_type"] = normalized
    return out


async def fetch_me(
    *,
    test_type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    GET /api/v1/me — joriy user / admin ma'lumoti.
    test_type berilsa, role bo'yicha aggregate'lar shu turdagi userlar bo'yicha qaytadi.
    """
    url = _build_url("/api/v1/me")
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = int(limit)
    if offset is not None:
        params["offset"] = int(offset)
    params = _with_test_type_param(params, test_type) or {}
    return await _request_json(
        "GET", url,
        params=params or None,
        headers=_auth_headers(extra_headers),
        timeout_total=DEFAULT_TIMEOUT_SEC,
        timeout_connect=DEFAULT_CONNECT_SEC,
    )


async def fetch_dtm_users(
    *,
    test_type: Optional[str] = None,
    district: Optional[str] = None,
    school_code: Optional[str] = None,
    group_name: Optional[str] = None,
    has_result: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """GET /api/v1/dtm/users — admin user ro'yxati, test_type bo'yicha filterlash mumkin."""
    url = _build_url("/api/v1/dtm/users")
    params: Dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if district:
        params["district"] = district
    if school_code:
        params["school_code"] = school_code
    if group_name:
        params["group_name"] = group_name
    if has_result is not None:
        params["has_result"] = "true" if has_result else "false"
    if search:
        params["search"] = search
    params = _with_test_type_param(params, test_type) or params
    return await _request_json(
        "GET", url,
        params=params,
        headers=_auth_headers(),
        timeout_total=DEFAULT_TIMEOUT_SEC,
        timeout_connect=DEFAULT_CONNECT_SEC,
    )


async def fetch_dtm_user(user_id: int) -> Dict[str, Any]:
    """GET /api/v1/dtm/user/{id} — bitta user (admin)."""
    url = _build_url(f"/api/v1/dtm/user/{int(user_id)}")
    return await _request_json(
        "GET", url,
        headers=_auth_headers(),
        timeout_total=DEFAULT_TIMEOUT_SEC,
        timeout_connect=DEFAULT_CONNECT_SEC,
    )


async def fetch_pending_bot_id_registrations(
    *,
    test_type: Optional[str] = None,
) -> Dict[str, Any]:
    """GET /api/v1/auth/pending-bot-id-registrations — kutilayotgan ro'yxatlar."""
    url = _build_url("/api/v1/auth/pending-bot-id-registrations")
    params = _with_test_type_param(None, test_type)
    return await _request_json(
        "GET", url,
        params=params,
        headers=_auth_headers(),
        timeout_total=DEFAULT_TIMEOUT_SEC,
        timeout_connect=DEFAULT_CONNECT_SEC,
    )


def filter_users_by_test_type(
    users: Iterable[Dict[str, Any]],
    test_type: Optional[str],
) -> list:
    """
    Klient tomonidan test_type bo'yicha filtrlash (backend qo'llab-quvvatlamasa).
    'offline' so'rovi NULL ni ham qabul qiladi.
    """
    if test_type is None:
        return list(users)
    normalized = normalize_test_type(test_type)
    out = []
    for u in users:
        if not isinstance(u, dict):
            continue
        ut = extract_test_type(u)
        if ut == normalized:
            out.append(u)
    return out


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

    req_headers = _auth_headers()
    masked_key = (req_headers.get("x-api-key") or "")[:8] + "..."
    logger.info(
        f"[DTM_READ] REQUEST url={DTM_READ_URL} book_id={book_id} "
        f"filename={actual_filename} content_type={actual_content_type} "
        f"image_size={len(image_bytes)} x-api-key={masked_key}"
    )

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(DTM_READ_URL, data=form, headers=req_headers) as r:
                text = await r.text()
                try:
                    data = await r.json()
                except Exception:
                    data = None

                if r.status >= 400:
                    logger.error("[DTM_READ] failed status=%s", r.status)
                    return {"ok": False, "status": r.status, "text": text, "data": data}

                logger.info("[DTM_READ] ok status=%s", r.status)
                return {
                    "ok": True,
                    "status": r.status,
                    "data": data,
                    "text": text,
                }
    except asyncio.TimeoutError:
        logger.error("[DTM_READ] timeout — server javob bermadi")
        return {"ok": False, "status": 0, "text": "timeout", "data": None}
    except aiohttp.ClientError as e:
        logger.error("[DTM_READ] network error: %s", type(e).__name__)
        return {"ok": False, "status": 0, "text": f"network error: {type(e).__name__}", "data": None}
    except Exception as e:
        logger.error("[DTM_READ] unexpected error: %s", type(e).__name__)
        return {"ok": False, "status": 0, "text": f"error: {type(e).__name__}", "data": None}


async def get_dtm_result(document_code):
    """
    Yangi API orqali natijani olib beradi.
    GET /api/v1/dtm/result/{document_code}
    """
    secret_key = (SECRET_KEY or "").strip()
    headers = {
        "x-api-key": secret_key,
        "accept": "application/json"
    }

    logger.info(f"[get_dtm_result] request document_code={document_code}")

    res = await _request_json_lb("GET", f"/dtm/result/by_chat/{document_code}", headers=headers)
    
    logger.info(f"[get_dtm_result] response ok={res.get('ok')} status={res.get('status')}")
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


_TEST_TYPE_COLUMN_MISSING = False


def check_user_exists_by_type(chat_id, test_type: str = DEFAULT_TEST_TYPE):
    """
    User bazada (chat_id, test_type) juftligi bilan borligini tekshiradi.
    True = registratsiya bor, False = registratsiya yo'q (yoki DB xato).

    Eslatma: backend "offline" so'rovi NULL larga ham mos kelishi kerak deb
    belgilagan (legacy userlar test_type=NULL bilan saqlangan). Shuning uchun
    'offline' uchun NULL-aware tekshiruv qilamiz.

    Agar local DB'da hali `test_type` ustuni bo'lmasa (eski schema):
      - 'offline' uchun: shu chat_id bo'yicha har qanday row borligini tekshiramiz
        (legacy DB faqat offline registratsiyalarni saqlagan).
      - 'online' uchun: column yo'q — biz aniq bilolmayotgan vaziyat. False
        qaytaramiz, FSM flow ishlasin (backend duplicate'ni o'zi tekshiradi).
    """
    import os
    import psycopg2
    from psycopg2 import errors as pg_errors

    global _TEST_TYPE_COLUMN_MISSING

    db_name = os.getenv("db_name")
    if db_name:
        db_name = db_name.strip('"')

    normalized = normalize_test_type(test_type)

    if _TEST_TYPE_COLUMN_MISSING:
        # Cached fallback — column doesn't exist in this DB.
        if normalized == DEFAULT_TEST_TYPE:
            return check_user_exists(chat_id)
        return False

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
                if normalized == DEFAULT_TEST_TYPE:
                    cur.execute(
                        """
                        SELECT id FROM users
                        WHERE chat_id = %s
                          AND (test_type = %s OR test_type IS NULL)
                        LIMIT 1
                        """,
                        (str(chat_id), normalized),
                    )
                else:
                    cur.execute(
                        "SELECT id FROM users WHERE chat_id = %s AND test_type = %s LIMIT 1",
                        (str(chat_id), normalized),
                    )
                return cur.fetchone() is not None
    except pg_errors.UndefinedColumn as e:
        _TEST_TYPE_COLUMN_MISSING = True
        logger.warning(
            "users.test_type column missing in local DB; falling back to chat_id-only "
            "lookup for offline and to FSM flow for online (err=%s)", e,
        )
        if normalized == DEFAULT_TEST_TYPE:
            return check_user_exists(chat_id)
        return False
    except Exception as e:
        print(f"DATABASE CHECK_USER_BY_TYPE ERROR => {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            conn.close()


# =========================
# mentalaba offline-test-results (sertifikat)
# =========================
def _mentalaba_headers() -> Dict[str, str]:
    """api.mentalaba.uz uchun: Bearer JWT + x-api-key."""
    from data.config import MENTALABA_API_KEY, MENTALABA_BEARER
    headers: Dict[str, str] = {
        "accept": "application/json",
        "content-type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; DTM-Bot/1.0)",
    }
    key = (MENTALABA_API_KEY or "").strip()
    if key:
        headers["x-api-key"] = key
    token = (MENTALABA_BEARER or "").strip()
    if token:
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return headers


async def create_offline_test_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST /v1/offline-test-results — natijani mentalaba'ga yuboradi (sertifikat).

    payload majburiy maydonlari (CreateOfflineTestResultDto):
      full_name, phone, school, primary_subject, secondary_subject,
      primary_subject_score, secondary_subject_score, mandatory_subject_score,
      total_score, admission_year.

    Auth (API_KEY/BEARER) sozlanmagan bo'lsa — so'rov yuborilmaydi, skip.
    """
    from data.config import MENTALABA_API_BASE, MENTALABA_API_KEY, MENTALABA_BEARER

    if not ((MENTALABA_API_KEY or "").strip() or (MENTALABA_BEARER or "").strip()):
        logger.warning("[mentalaba] API_KEY/BEARER sozlanmagan — offline-test-results skip")
        return {"ok": False, "status": 0, "text": "mentalaba auth not configured", "skipped": True}

    base = (MENTALABA_API_BASE or "https://api.mentalaba.uz").rstrip("/")
    url = f"{base}/v1/offline-test-results"
    res = await _request_json(
        "POST", url,
        json_data=payload,
        headers=_mentalaba_headers(),
        timeout_total=DEFAULT_TIMEOUT_SEC,
        timeout_connect=DEFAULT_CONNECT_SEC,
    )
    if res.get("ok"):
        logger.info("[mentalaba] offline-test-result created: %s", str(res.get("data"))[:300])
    else:
        logger.error("[mentalaba] create failed status=%s text=%s", res.get("status"), str(res.get("text"))[:300])
    return res


# =========================
# Admin Panel API — majburiy obuna kanallari
# =========================
SUBSCRIPTIONS_CACHE_TTL = int(os.getenv("SUBSCRIPTIONS_CACHE_TTL", "45"))

_subs_cache: Dict[str, Any] = {"channels": [], "ts": 0.0}
_bot_db_id_cache: Dict[str, Any] = {"id": None, "resolved": False}


async def _resolve_bot_db_id(bot_username: Optional[str] = None) -> Optional[str]:
    """BOT_DB_ID .env'da qo'lda berilgan bo'lsa — o'shani ishlatadi.
    Aks holda GET /api/v1/admin/bots ro'yxatidan shu botni token_preview
    yoki username orqali topib, jarayon davomida keshlaydi (bir marta so'rov)."""
    manual = (BOT_DB_ID or "").strip()
    if manual:
        return manual

    if _bot_db_id_cache["resolved"]:
        return _bot_db_id_cache["id"]

    token = (ADMIN_TOKEN or "").strip()
    if not token:
        return None

    base = (ADMIN_API_BASE or "").rstrip("/")
    res = await _request_json(
        "GET", f"{base}/api/v1/admin/bots",
        headers={"X-Admin-Token": token},
        timeout_total=DEFAULT_TIMEOUT_SEC,
        timeout_connect=DEFAULT_CONNECT_SEC,
    )
    bots = res.get("data") if res.get("ok") else None
    if not isinstance(bots, list):
        logger.warning("[subs] bots list fetch failed status=%s", res.get("status"))
        return None

    my_token = (BOT_TOKEN or "").strip()
    found = None
    for b in bots:
        preview = str(b.get("token_preview") or "").strip().rstrip(".")
        if preview and my_token and my_token.startswith(preview):
            found = b
            break
    if not found and bot_username:
        uname = bot_username.lstrip("@").lower()
        for b in bots:
            name = str(b.get("name") or "").lstrip("@").lower()
            if name == uname:
                found = b
                break
    if not found and len(bots) == 1:
        # token_preview/name formati noma'lum bo'lsa ham, bitta bot bo'lsa
        # taxmin qilishning hojati yo'q — o'shani ishlatamiz.
        found = bots[0]

    if found:
        _bot_db_id_cache["id"] = str(found["id"])
        logger.info("[subs] auto-resolved bot_db_id=%s (name=%s)", found["id"], found.get("name"))
    else:
        logger.warning("[subs] bot topilmadi admin panel ro'yxatida (token_preview/name mos kelmadi)")
    _bot_db_id_cache["resolved"] = True
    return _bot_db_id_cache["id"]


async def fetch_active_subscriptions(force: bool = False, bot_username: Optional[str] = None) -> list:
    """GET /api/v1/admin/bots/{bot_id}/subscriptions/active — majburiy kanallar.

    30-60s cache qilinadi (docs/bot-subscription-check.md). bot_id qo'lda
    (BOT_DB_ID) yoki avtomatik (token_preview/username orqali) aniqlanadi.
    ADMIN_TOKEN sozlanmagan yoki bot_id topilmasa — bo'sh ro'yxat (majburiy
    kanal yo'q deb hisoblanadi). Backend/tarmoq xatosida ham eski cache
    (agar bor bo'lsa) qaytariladi — bitta uzilish barcha userlarni bloklab qo'ymasin.
    """
    now = asyncio.get_event_loop().time()
    if not force and (now - _subs_cache["ts"]) < SUBSCRIPTIONS_CACHE_TTL:
        return _subs_cache["channels"]

    token = (ADMIN_TOKEN or "").strip()
    if not token:
        return _subs_cache["channels"]

    bot_id = await _resolve_bot_db_id(bot_username)
    if not bot_id:
        return _subs_cache["channels"]

    base = (ADMIN_API_BASE or "").rstrip("/")
    url = f"{base}/api/v1/admin/bots/{bot_id}/subscriptions/active"
    res = await _request_json(
        "GET", url,
        headers={"X-Admin-Token": token},
        timeout_total=DEFAULT_TIMEOUT_SEC,
        timeout_connect=DEFAULT_CONNECT_SEC,
    )
    if res.get("ok") and isinstance(res.get("data"), list):
        _subs_cache["channels"] = res["data"]
        _subs_cache["ts"] = now
    else:
        logger.warning("[subs] fetch failed status=%s text=%s", res.get("status"), str(res.get("text"))[:200])
    return _subs_cache["channels"]
