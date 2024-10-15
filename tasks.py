from kojisession import KojiSession
from enum import IntEnum
import asyncio
from util import error

class TaskState(IntEnum):
    FREE = 0
    OPEN = 1
    CLOSED = 2
    CANCELLED = 3
    ASSIGNED = 4
    FAILED = 5


class TaskWatcher:

    def __init__(self, session, task_id: int):
        self.id = task_id
        self.session = session
        self.info = dict()

    def update(self):
        self.info = self.session.getTaskInfo(task_id=self.id, request=True)
    
    def is_done(self):
        self.update()
        if self.info is None:
            return False
        state = self.info['state']
        return (state in [TaskState.CLOSED, TaskState.CANCELLED, TaskState.FAILED])
    

async def watch_task(session, task_id, poll_interval: int = 900):
    """
    :param session - koji client session object
    :param task_id - task id
    :param poll_interval - polling interval in seconds
    """
    task = TaskWatcher(session, task_id)
    while True:
        if task.is_done():
            break
        # Go to sleep and check task status again after poll_interval
        await asyncio.sleep(poll_interval)

    return task.info['state']

