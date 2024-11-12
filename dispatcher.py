import asyncio
import logging
from notification import Notification
from rebuild import Rebuild, BuildState
from util import whoami


async def task_dispatcher(
    upstream, downstream, packages: list, notify: Notification | None = None
):
    logger = logging.getLogger(whoami())

    task_queue = list()

    # XXX: Currently checking only one arch
    arches = (downstream.instance["arches"])[0]
    rebuild = Rebuild(upstream, downstream)

    def get_taskurl(session, task_id):
        url = session.config["weburl"]
        url += f"taskinfo?taskID={task_id}"
        return url

    while packages or task_queue:
        ready = downstream.get_ready_hosts(arches)

        while len(task_queue) < ready:
            build_task = asyncio.create_task(rebuild.rebuild_package(packages.pop(0)))
            task_queue.append(build_task)

        done, _ = await asyncio.wait(task_queue, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            pkg, task_id, result = await task

            if result == BuildState.FAILED:
                logger.critical("Package %s build failed!" % pkg)
            elif result == BuildState.CANCELLED:
                logger.info("Package %s build cancelled" % pkg)
            elif result == BuildState.COMPLETE:
                logger.info("Package %s build complete" % pkg)

            if isinstance(notify, Notification):
                taskurl = get_taskurl(downstream, task_id)
                await notify.build_notify(result, taskurl)

            task_queue.remove(task)
