import logging
import asyncio
import click

from .util import GenericException
from .setup import Setup
from .notification import Notification
from .dispatcher import TaskDispatcher


@click.command("koji-rebuild")
@click.argument(
    "configfile", type=click.Path(exists=True, dir_okay=False, resolve_path=True)
)
def main(configfile):
    """
    CONFIGFILE: YAML formatted configuration file
    """
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
    except GenericException as e:
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


if __name__ == "__main__":
    main()
