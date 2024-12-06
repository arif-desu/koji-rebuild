#! usr/bin/env python3
import sys
import logging
import asyncio

import util
from setup import Setup
from notification import Notification
from dispatcher import TaskDispatcher


if __name__ == "__main__":
    try:
        configfile = sys.argv[1]
    except IndexError:
        sys.exit("YAML config file must specified as command-line argument!")

    config = Setup(configfile)

    logger = logging.getLogger("main")

    logfile = config.setup_logger(append_date=True)
    upstream = config.get_koji_session("upstream")
    downstream = config.get_koji_session("downstream")
    packages = config.get_packagelist()
    notify = config.setup_notifications()
    max_jobs = config.max_tasks

    dispatcher = TaskDispatcher(upstream, downstream, packages, notify, max_jobs)

    msg = str()
    try:
        asyncio.run(dispatcher.start())
    except KeyboardInterrupt:
        msg = "Received SIGINT from keyboard"
        logger.exception(msg)
    except util.GenericException as e:
        msg = e.__str__()
    else:
        msg = "All packages built!"
    finally:
        if isinstance(notify, Notification):
            asyncio.run(
                notify.send_email(
                    "Koji Build System: Finished", msg, attachment=[logfile]
                )
            )
        print(msg)
