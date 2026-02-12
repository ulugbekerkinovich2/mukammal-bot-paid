import aiohttp

# BASE_URL ni o'zingni configdan ol
from data.config import BASE_URL


async def fetch_districts(region: str):
    """
    Kutiladigan response:
      {"type":"districts","data":["Shayxontohur tumani", ...]}
    """
    url = f"{BASE_URL}/admin/districts-and-schools"
    params = {"region": region}

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as r:
            text = await r.text()
            if r.status >= 400:
                return {"ok": False, "status": r.status, "text": text}
            try:
                payload = await r.json()
            except Exception:
                return {"ok": False, "status": r.status, "text": text}

    if not isinstance(payload, dict) or payload.get("type") != "districts":
        return {"ok": False, "status": 500, "text": f"Unexpected payload: {payload}"}

    return {"ok": True, "districts": payload.get("data") or []}


async def fetch_schools(region: str, district: str):
    """
    Kutiladigan response:
      {"type":"schools","data":[{"id":1,"code":"SHAY10","name":"10 maktab"}, ...]}
    """
    url = f"{BASE_URL}/admin/districts-and-schools"
    params = {"region": region, "district": district}

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as r:
            text = await r.text()
            if r.status >= 400:
                return {"ok": False, "status": r.status, "text": text}
            try:
                payload = await r.json()
            except Exception:
                return {"ok": False, "status": r.status, "text": text}

    if not isinstance(payload, dict) or payload.get("type") != "schools":
        return {"ok": False, "status": 500, "text": f"Unexpected payload: {payload}"}

    return {"ok": True, "schools": payload.get("data") or []}
