import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


@dataclass
class Job:
    coro_factory: Callable[[], Awaitable[Any]]
    future: asyncio.Future


class JobQueue:
    """
    In-memory queue:
    - workers: nechta worker parallel ishlaydi (job darajasida)
    - maxsize: navbat limiti (navbat to'lsa, submit kutadi)
    """
    def __init__(self, *, workers: int = 10, maxsize: int = 2000):
        self._q: asyncio.Queue[Job] = asyncio.Queue(maxsize=maxsize)
        self._workers = workers
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        for _ in range(self._workers):
            self._tasks.append(asyncio.create_task(self._worker()))

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def submit(self, coro_factory: Callable[[], Awaitable[Any]]) -> Any:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        await self._q.put(Job(coro_factory=coro_factory, future=fut))
        return await fut

    async def _worker(self):
        while True:
            job = await self._q.get()
            try:
                res = await job.coro_factory()
                if not job.future.done():
                    job.future.set_result(res)
            except Exception as e:
                if not job.future.done():
                    job.future.set_exception(e)
            finally:
                self._q.task_done()
