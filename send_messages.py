# import requests
# import time
# import logging

# BOT_TOKEN = "8065746866:AAExtwjKRnCMOsSdvQ5t5dvSSXhMmba0iZI"
# print("SCRIPT STARTED", flush=True)

# # BOT_TOKEN = "YOUR_BOT_TOKEN"
# SOURCE_CHAT_ID = -1003869260595
# MESSAGE_ID = 473
# USER_IDS = [44091892, 935920479]

# BASE_URL = "https://api.telegram.org/bot{}".format(BOT_TOKEN)

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s"
# )
# logger = logging.getLogger(__name__)


# def copy_post_to_user(user_id):
#     url = "{}/copyMessage".format(BASE_URL)
#     payload = {
#         "chat_id": user_id,
#         "from_chat_id": SOURCE_CHAT_ID,
#         "message_id": MESSAGE_ID,
#         "disable_notification": False
#     }

#     print("[PRINT] Sending to user_id={}".format(user_id), flush=True)
#     logger.info("Yuborish boshlandi | user_id=%s", user_id)

#     resp = requests.post(url, json=payload, timeout=30)

#     print("[PRINT] status_code={}".format(resp.status_code), flush=True)
#     logger.info("Telegram status_code=%s", resp.status_code)

#     try:
#         data = resp.json()
#     except Exception:
#         data = {"raw_text": resp.text}

#     print("[PRINT] response={}".format(data), flush=True)
#     logger.info("Telegram response=%s", data)

#     if isinstance(data, dict) and data.get("ok"):
#         print("[PRINT] SUCCESS user_id={}".format(user_id), flush=True)
#         logger.info("Muvaffaqiyatli yuborildi | user_id=%s", user_id)
#     else:
#         print("[PRINT] ERROR user_id={} data={}".format(user_id, data), flush=True)
#         logger.error("Xato | user_id=%s | data=%s", user_id, data)


# def main():
#     print("MAIN STARTED", flush=True)
#     logger.info("main() ishga tushdi")
#     logger.info("USER_IDS=%s", USER_IDS)

#     for i, user_id in enumerate(USER_IDS, 1):
#         print("[PRINT] {}/{} -> {}".format(i, len(USER_IDS), user_id), flush=True)
#         try:
#             copy_post_to_user(user_id)
#             time.sleep(0.5)
#         except Exception as e:
#             print("[PRINT] EXCEPTION user_id={} error={}".format(user_id, e), flush=True)
#             logger.exception("Exception | user_id=%s | error=%s", user_id, e)

#     print("MAIN FINISHED", flush=True)
#     logger.info("Hammasi tugadi")


# if __name__ == "__main__":
#     print("__main__ block entered", flush=True)
#     main()
# import requests
# import time
# import logging
# import json

# with open("mt_test_users.json", 'r', encoding="utf-8") as f:
#     mt_test_users = json.load(f)
# BOT_TOKEN = "8065746866:AAExtwjKRnCMOsSdvQ5t5dvSSXhMmba0iZI"

# # Reklama post chiqqan kanal
# SOURCE_CHAT_ID = -1002499834980
# MESSAGE_ID = 263

# # Test userlar
# USER_IDS = [44091892, 935920479]

# BASE_URL = "https://api.telegram.org/bot{}".format(BOT_TOKEN)

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s"
# )
# logger = logging.getLogger(__name__)


# def forward_post_to_user(user_id):
#     url = "{}/forwardMessage".format(BASE_URL)
#     payload = {
#         "chat_id": user_id,
#         "from_chat_id": SOURCE_CHAT_ID,
#         "message_id": MESSAGE_ID,
#         "disable_notification": False
#     }

#     logger.info(
#         "Forward boshlandi | user_id=%s | from_chat_id=%s | message_id=%s",
#         user_id, SOURCE_CHAT_ID, MESSAGE_ID
#     )

#     resp = requests.post(url, json=payload, timeout=30)

#     logger.info("Telegram status_code=%s", resp.status_code)

#     try:
#         data = resp.json()
#     except Exception:
#         data = {"raw_text": resp.text}

#     logger.info("Telegram response=%s", data)

#     if data.get("ok"):
#         logger.info("Muvaffaqiyatli forward qilindi | user_id=%s", user_id)
#         print("SUCCESS -> {}".format(user_id))
#     else:
#         logger.error("Forward xato | user_id=%s | data=%s", user_id, data)
#         print("ERROR -> {} | {}".format(user_id, data))


# def main():
#     logger.info("Yuborish boshlandi | total_users=%s", len(USER_IDS))

#     for user_id in USER_IDS:
#         try:
#             forward_post_to_user(user_id)
#             time.sleep(0.5)
#         except Exception as e:
#             logger.exception("Exception | user_id=%s | error=%s", user_id, e)
#             print("EXCEPTION -> {} | {}".format(user_id, e))

#     logger.info("Yuborish tugadi")


# if __name__ == "__main__":
#     main()


# -*- coding: utf-8 -*-
import os
import json
import time
import random
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

import requests
with open("mt_test_users.json", 'r', encoding="utf-8") as f:
    mt_test_users = json.load(f)
# =========================
# CONFIG
# =========================
BOT_TOKEN = "8065746866:AAExtwjKRnCMOsSdvQ5t5dvSSXhMmba0iZI"
BASE_URL = "https://api.telegram.org/bot{}".format(BOT_TOKEN)


SOURCE_CHAT_ID = -1002499834980
MESSAGE_ID = 263

DISABLE_NOTIFICATION = False
# USER_IDS = [
#     44091892,
#     935920479,
# ]
user_ids = [ int(i['bot_id']) for i in mt_test_users]
USER_IDS = user_ids
# Telegramni bezovta qilmaslik uchun sekinroq yuboramiz
BASE_DELAY_SECONDS = 1.2
JITTER_MIN_SECONDS = 0.2
JITTER_MAX_SECONDS = 0.8

# retry sozlamalari
MAX_RETRIES = 4
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# fayllar
OUTPUT_DIR = "forward_reports"
LOG_FILE = os.path.join(OUTPUT_DIR, "forward.log")
RESULTS_FILE = os.path.join(OUTPUT_DIR, "forward_results.jsonl")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "forward_summary.json")

# qayta ishga tushganda oldin yuborilganlarni skip qilish
RESUME_FROM_PREVIOUS = True


# =========================
# SETUP
# =========================
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def utc_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def setup_logger():
    ensure_dir(OUTPUT_DIR)

    logger = logging.getLogger("forward_sender")
    logger.setLevel(logging.INFO)
    logger.handlers = []

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


logger = setup_logger()


# =========================
# FILE HELPERS
# =========================
def atomic_write_json(path, data):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_processed_user_ids(path):
    processed = set()

    if not os.path.exists(path):
        return processed

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
                user_id = item.get("user_id")
                status = item.get("status")
                if user_id is not None and status in (
                    "success",
                    "blocked",
                    "chat_not_found",
                    "user_deactivated",
                    "source_error",
                    "forbidden",
                    "api_error",
                    "network_error",
                ):
                    processed.add(int(user_id))
            except Exception:
                continue

    return processed


# =========================
# TELEGRAM ERROR CLASSIFIER
# =========================
def classify_error(status_code, data):
    description = str(data.get("description", "")).lower()
    error_code = data.get("error_code", status_code)

    if error_code == 429 or "too many requests" in description:
        return "rate_limited"

    if "blocked by the user" in description:
        return "blocked"

    if "chat not found" in description:
        return "chat_not_found"

    if "user is deactivated" in description or "user deactivated" in description:
        return "user_deactivated"

    if "message to forward not found" in description:
        return "source_error"

    if "message_id is not specified" in description:
        return "source_error"

    if "have no rights" in description:
        return "source_error"

    if error_code == 403:
        return "forbidden"

    if 500 <= int(status_code) < 600:
        return "server_error"

    return "api_error"


# =========================
# SUMMARY
# =========================
def make_summary(total_users):
    return {
        "started_at": now_str(),
        "updated_at": now_str(),
        "total_users": total_users,
        "processed": 0,
        "success": 0,
        "blocked": 0,
        "chat_not_found": 0,
        "user_deactivated": 0,
        "forbidden": 0,
        "source_error": 0,
        "rate_limited": 0,
        "server_error": 0,
        "api_error": 0,
        "network_error": 0,
        "skipped": 0,
        "remaining": total_users,
    }


def update_summary(summary, result_status):
    summary["processed"] += 1
    if result_status in summary:
        summary[result_status] += 1
    else:
        summary["api_error"] += 1

    summary["remaining"] = max(summary["total_users"] - summary["processed"] - summary["skipped"], 0)
    summary["updated_at"] = now_str()


def increment_skipped(summary, count=1):
    summary["skipped"] += count
    summary["remaining"] = max(summary["total_users"] - summary["processed"] - summary["skipped"], 0)
    summary["updated_at"] = now_str()


def log_progress(summary):
    logger.info(
        "PROGRESS | processed=%s/%s | success=%s | blocked=%s | chat_not_found=%s | "
        "deactivated=%s | forbidden=%s | source_error=%s | api_error=%s | network_error=%s | skipped=%s | remaining=%s",
        summary["processed"],
        summary["total_users"],
        summary["success"],
        summary["blocked"],
        summary["chat_not_found"],
        summary["user_deactivated"],
        summary["forbidden"],
        summary["source_error"],
        summary["api_error"],
        summary["network_error"],
        summary["skipped"],
        summary["remaining"],
    )


# =========================
# SENDER
# =========================
def sleep_between_requests():
    delay = BASE_DELAY_SECONDS + random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
    time.sleep(delay)


def extract_retry_after(data):
    try:
        params = data.get("parameters", {}) or {}
        retry_after = int(params.get("retry_after", 0))
        if retry_after > 0:
            return retry_after
    except Exception:
        pass
    return None


def forward_post_to_user(session, user_id):
    url = "{}/forwardMessage".format(BASE_URL)

    payload = {
        "chat_id": user_id,
        "from_chat_id": SOURCE_CHAT_ID,
        "message_id": MESSAGE_ID,
        "disable_notification": DISABLE_NOTIFICATION
    }

    logger.info(
        "Forward boshlandi | user_id=%s | from_chat_id=%s | message_id=%s",
        user_id, SOURCE_CHAT_ID, MESSAGE_ID
    )

    attempt = 0
    last_error = None

    while attempt < MAX_RETRIES:
        attempt += 1

        try:
            resp = session.post(
                url,
                json=payload,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
            )

            logger.info(
                "Telegram javobi | user_id=%s | attempt=%s/%s | status_code=%s",
                user_id, attempt, MAX_RETRIES, resp.status_code
            )

            try:
                data = resp.json()
            except Exception:
                data = {
                    "ok": False,
                    "description": "Non-JSON response",
                    "raw_text": resp.text
                }

            logger.info("Telegram response | user_id=%s | data=%s", user_id, data)

            if data.get("ok"):
                return {
                    "status": "success",
                    "ok": True,
                    "attempt": attempt,
                    "status_code": resp.status_code,
                    "response": data
                }

            error_type = classify_error(resp.status_code, data)
            description = str(data.get("description", ""))

            # Rate limit bo'lsa kutib retry qilamiz
            if error_type == "rate_limited":
                retry_after = extract_retry_after(data)
                wait_seconds = retry_after if retry_after is not None else (5 * attempt)

                logger.warning(
                    "Rate limit | user_id=%s | attempt=%s/%s | retry_after=%s sec | desc=%s",
                    user_id, attempt, MAX_RETRIES, wait_seconds, description
                )

                if attempt < MAX_RETRIES:
                    time.sleep(wait_seconds + random.uniform(0.5, 1.5))
                    continue

            # vaqtinchalik server xatolari
            if error_type == "server_error":
                wait_seconds = 2 * attempt
                logger.warning(
                    "Telegram server error | user_id=%s | attempt=%s/%s | wait=%s sec | desc=%s",
                    user_id, attempt, MAX_RETRIES, wait_seconds, description
                )

                if attempt < MAX_RETRIES:
                    time.sleep(wait_seconds)
                    continue

            # blok, chat not found va shunga o‘xshashlar retry qilinmaydi
            return {
                "status": error_type,
                "ok": False,
                "attempt": attempt,
                "status_code": resp.status_code,
                "response": data
            }

        except requests.exceptions.Timeout as e:
            last_error = str(e)
            logger.warning(
                "Timeout | user_id=%s | attempt=%s/%s | error=%s",
                user_id, attempt, MAX_RETRIES, e
            )
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
                continue

        except requests.exceptions.ConnectionError as e:
            last_error = str(e)
            logger.warning(
                "ConnectionError | user_id=%s | attempt=%s/%s | error=%s",
                user_id, attempt, MAX_RETRIES, e
            )
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
                continue

        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logger.warning(
                "RequestException | user_id=%s | attempt=%s/%s | error=%s",
                user_id, attempt, MAX_RETRIES, e
            )
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
                continue

        except Exception as e:
            last_error = str(e)
            logger.exception(
                "Unexpected exception | user_id=%s | attempt=%s/%s | error=%s",
                user_id, attempt, MAX_RETRIES, e
            )
            break

    return {
        "status": "network_error",
        "ok": False,
        "attempt": attempt,
        "status_code": None,
        "response": {
            "description": last_error or "Unknown network error"
        }
    }


# =========================
# MAIN
# =========================
def main():
    ensure_dir(OUTPUT_DIR)

    summary = make_summary(len(USER_IDS))
    atomic_write_json(SUMMARY_FILE, summary)

    session = requests.Session()

    processed_users = set()
    if RESUME_FROM_PREVIOUS:
        processed_users = load_processed_user_ids(RESULTS_FILE)
        if processed_users:
            logger.info("Resume rejimi | oldin yuborilgan/skipped userlar soni=%s", len(processed_users))

    logger.info("Yuborish boshlandi | total_users=%s", len(USER_IDS))

    for idx, user_id in enumerate(USER_IDS, start=1):
        try:
            if RESUME_FROM_PREVIOUS and int(user_id) in processed_users:
                logger.info("SKIP | user_id=%s | sabab=already_processed", user_id)
                increment_skipped(summary, 1)
                atomic_write_json(SUMMARY_FILE, summary)
                continue

            result = forward_post_to_user(session, user_id)

            row = {
                "timestamp": utc_iso(),
                "index": idx,
                "user_id": user_id,
                "from_chat_id": SOURCE_CHAT_ID,
                "message_id": MESSAGE_ID,
                "status": result["status"],
                "ok": result["ok"],
                "attempt": result["attempt"],
                "status_code": result["status_code"],
                "response": result["response"]
            }

            append_jsonl(RESULTS_FILE, row)

            update_summary(summary, result["status"])
            atomic_write_json(SUMMARY_FILE, summary)

            if result["ok"]:
                logger.info("SUCCESS | user_id=%s", user_id)
                print("SUCCESS -> {}".format(user_id))
            else:
                logger.error(
                    "FAILED | user_id=%s | status=%s | response=%s",
                    user_id, result["status"], result["response"]
                )
                print("ERROR -> {} | {}".format(user_id, result["status"]))

            log_progress(summary)

            # keyingi so'rovdan oldin biroz kutamiz
            sleep_between_requests()

        except Exception as e:
            logger.exception("Main loop exception | user_id=%s | error=%s", user_id, e)

            row = {
                "timestamp": utc_iso(),
                "index": idx,
                "user_id": user_id,
                "from_chat_id": SOURCE_CHAT_ID,
                "message_id": MESSAGE_ID,
                "status": "network_error",
                "ok": False,
                "attempt": 0,
                "status_code": None,
                "response": {
                    "description": str(e)
                }
            }

            append_jsonl(RESULTS_FILE, row)
            update_summary(summary, "network_error")
            atomic_write_json(SUMMARY_FILE, summary)
            log_progress(summary)

            # xatoda ham to'xtamaydi, davom etadi
            sleep_between_requests()
            continue

    summary["finished_at"] = now_str()
    atomic_write_json(SUMMARY_FILE, summary)
    logger.info("Yuborish tugadi | summary=%s", summary)


if __name__ == "__main__":
    main()