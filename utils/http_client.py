import asyncio
from typing import Any, Dict, Optional
import aiohttp


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


class HttpClient:
    """
    - max_concurrency: bir vaqtning o'zida nechta HTTP so'rov chiqishi mumkin
    - timeout: umumiy kutish vaqti
    - retry: vaqtinchalik xatolarda qayta urinish
    """
    def __init__(
        self,
        *,
        max_concurrency: int = 20,
        timeout_total: int = 30,
        timeout_connect: int = 5,
        retry: int = 3,
    ):
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout = aiohttp.ClientTimeout(total=timeout_total, connect=timeout_connect)
        self._retry = retry
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if self._session is None or self._session.closed:
            await self.start()

        # default headers
        h = {"Accept": "application/json", "Connection": "close"}
        if headers:
            h.update(headers)

        async with self._sem:
            last_exc: Optional[Exception] = None

            for attempt in range(self._retry):
                try:
                    async with self._session.request(method, url, json=json_data, headers=h) as resp:
                        text = await resp.text()

                        # 5xx -> retry qilish mumkin
                        if resp.status >= 500:
                            raise HttpError(resp.status, text)

                        # 4xx -> odatda retry qilinmaydi (payload/validation/auth)
                        if resp.status >= 400:
                            return {"ok": False, "status": resp.status, "text": text}

                        # success
                        try:
                            data = await resp.json()
                            return {"ok": True, "status": resp.status, "data": data}
                        except Exception:
                            return {"ok": True, "status": resp.status, "raw": text}

                except (aiohttp.ClientError, HttpError) as e:
                    last_exc = e
                    # exponential-ish backoff
                    await asyncio.sleep(0.6 * (attempt + 1))

            # hammasi tugasa
            raise last_exc or RuntimeError("HTTP request failed")
