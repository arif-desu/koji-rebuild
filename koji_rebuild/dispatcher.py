import asyncio
import logging
from .session import KojiSession
from .notification import Notification
from .rebuild import Rebuild, BuildState
from .util import error, resolvepath, whoami
from .configuration import Configuration


class TaskDispatcher:
    task_queue = list()
    logger = logging.getLogger(whoami())

    def __init__(
        self, upstream: KojiSession, downstream: KojiSession, packages: list
    ) -> None:
        self.downstream = downstream
        self.packages = packages
        self.settings = Configuration().settings

        self.max_tasks = self.settings["max_tasks"]

        alert = self.settings["notifications"]["alert"]
        if alert == "prompt":
            self.notifications = Notification()
        else:
            self.notifications = None

        logs = self.settings["logging"]

        self.complete_fd = open(resolvepath(logs["completed"]), mode="wt")
        self.failed_fd = open(resolvepath(logs["failed"]), mode="wt")

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

    def _add_tasks(self):
        while len(self.task_queue) <= self.max_tasks and self.packages:
            build_task = asyncio.create_task(
                self.rebuild.rebuild_package(self.packages.pop(0))
            )
            self.task_queue.append(build_task)

    async def start(self):
        completed_fd = open("completed.txt", "wt")
        failed_fd = open("failed.txt", "wt")
        while self.packages or self.task_queue:
            self._add_tasks()

            if len(self.task_queue) == 0:
                error("Task queue is empty!")

            done, _ = await asyncio.wait(
                self.task_queue, return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                pkg, task_id, result = task.result()

                if result == BuildState.FAILED:
                    failed_fd.write(pkg + "\n")
                    self.logger.critical("Package %s build failed!" % pkg)
                elif result == BuildState.CANCELLED:
                    self.logger.info("Package %s build cancelled" % pkg)
                elif result == BuildState.COMPLETE:
                    completed_fd.write(pkg + "\n")
                    self.logger.info("Package %s build complete" % pkg)

                # Attempt email notification
                if isinstance(self.notifications, Notification):
                    taskurl = self._get_taskurl(task_id)
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(
                            self.notifications.build_notify(pkg, result, taskurl)
                        )

                self.task_queue.remove(task)
