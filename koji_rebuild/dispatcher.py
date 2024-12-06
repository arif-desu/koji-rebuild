import asyncio
import logging
from .kojisession import KojiSession
from .notification import Notification
from .rebuild import Rebuild, BuildState
from .util import error, whoami


class TaskDispatcher:
    def __init__(
        self,
        upstream: KojiSession,
        downstream: KojiSession,
        packages: list,
        notifications: Notification | None = None,
        max_tasks: int = 10,
    ) -> None:
        self.task_queue = list()
        self.max_tasks = max_tasks
        self.logger = logging.getLogger(whoami())
        self.downstream = downstream
        self.packages = packages
        self.notifications = notifications
        self.rebuild = Rebuild(upstream, downstream)

    def _get_taskurl(self, task_id: int):
        if task_id <= 0:
            return None
        url = "%s/%s?%s=%d" % (
            self.downstream.config["weburl"],
            "taskinfo",
            "taskID",
            task_id,
        )
        return url

    def _append_tasks(self):
        while len(self.task_queue) <= self.max_tasks and self.packages:
            build_task = asyncio.create_task(
                self.rebuild.rebuild_package(self.packages.pop(0))
            )
            self.task_queue.append(build_task)

    async def start(self):
        while self.packages or self.task_queue:
            self._append_tasks()

            if len(self.task_queue) == 0:
                error("Task queue is empty!")

            done, _ = await asyncio.wait(
                self.task_queue, return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                pkg, task_id, result = task.result()

                if result == BuildState.FAILED:
                    self.logger.critical("Package %s build failed!" % pkg)
                elif result == BuildState.CANCELLED:
                    self.logger.info("Package %s build cancelled" % pkg)
                elif result == BuildState.COMPLETE:
                    self.logger.info("Package %s build complete" % pkg)

                # Attempt email notification
                if isinstance(self.notifications, Notification):
                    taskurl = self._get_taskurl(task_id)
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(
                            self.notifications.build_notify(pkg, result, taskurl)
                        )

                self.task_queue.remove(task)
