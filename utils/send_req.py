import requests
from typing import Dict, Any
import random
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
    language: str = "uz",
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
        "language": language
    }

    # print(payload)
    try:
        response = session.post(MAIN_URL, json=payload, timeout=timeout)

        # ❗ HTTP xatolarni majburan chiqaramiz
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
