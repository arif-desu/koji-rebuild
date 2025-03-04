from enum import IntEnum
import asyncio
from .session import KojiSession


class TaskState(IntEnum):
    FREE = 0
    OPEN = 1
    CLOSED = 2
    CANCELLED = 3
    ASSIGNED = 4
    FAILED = 5


class TaskWatcher:

    def __init__(self, session: KojiSession, task_id: int):
        self.id = task_id
        self.session = session
        self.info = dict()

    def update(self):
        self.info = self.session.getTaskInfo(task_id=self.id, request=True)

    def is_done(self):
        self.update()
        if self.info is None:
            return False
        state = self.info["state"]
        return state in [TaskState.CLOSED, TaskState.CANCELLED, TaskState.FAILED]

    async def watch_task(self, poll_interval: int = 60) -> int:
        while True:
            if self.is_done():
                break
            else:
                await asyncio.sleep(poll_interval)

        return self.info["state"]
