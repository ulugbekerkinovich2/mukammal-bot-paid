import requests
from typing import Dict, Any

MAIN_URL = "https://dtm-api.misterdev.uz/api/v1/auth/register"

session = requests.Session()
session.headers.update({
    "Content-Type": "application/json",
    "Accept": "application/json",
})


def register(
    bot_id: str,
    full_name: str,
    phone: str,
    school_code: str,
    first_subject_id: int,
    second_subject_id: int,
    timeout: int = 10,
) -> Dict[str, Any]:
    payload = {
        "bot_id": bot_id,
        "full_name": full_name,
        "phone": phone,
        "school_code": school_code,
        "first_subject_id": first_subject_id,
        "second_subject_id": second_subject_id,
    }

    try:
        response = session.post(MAIN_URL, json=payload, timeout=timeout)
        response.raise_for_status()  # 4xx / 5xx ushlaydi
        return {
            "ok": True,
            "status_code": response.status_code,
            "data": response.json(),
        }

    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "error": "Request timeout. Please try again.",
        }

    except requests.exceptions.HTTPError as e:
        return {
            "ok": False,
            "status_code": response.status_code,
            "error": response.text,
        }

    except requests.exceptions.RequestException as e:
        return {
            "ok": False,
            "error": str(e),
        }
