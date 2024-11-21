import asyncio
import logging
from notification import Notification
from rebuild import Rebuild, BuildState
from util import whoami, error


async def task_dispatcher(
    upstream, downstream, packages: list, notify: Notification | None = None
):
    logger = logging.getLogger(whoami())

    task_queue = list()

    # XXX: Currently checking only one arch
    arch = (downstream.instance["arches"])[0]

    if downstream.get_total_hosts(arch) == 0:
        error(f"No builders available for architecture {arch}")

    rebuild = Rebuild(upstream, downstream)

    def get_taskurl(session, task_id: int):
        if task_id <= 0:
            return None
        url = "%s/%s?%s=%d" % (session.config["weburl"], "taskinfo", "taskID", task_id)
        return url

    while packages or task_queue:
        ready = downstream.get_ready_hosts(arch)

        while len(task_queue) < ready and packages:
            build_task = asyncio.create_task(rebuild.rebuild_package(packages.pop(0)))
            task_queue.append(build_task)

        done, _ = await asyncio.wait(task_queue, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            pkg, task_id, result = task.result()

            if result == BuildState.FAILED:
                logger.critical("Package %s build failed!" % pkg)
            elif result == BuildState.CANCELLED:
                logger.info("Package %s build cancelled" % pkg)
            elif result == BuildState.COMPLETE:
                logger.info("Package %s build complete" % pkg)

            if isinstance(notify, Notification):
                taskurl = get_taskurl(downstream, task_id)
                await notify.build_notify(pkg, result, taskurl)

            task_queue.remove(task)
