import logging
import asyncio
import click

from .session import KojiSession
from .util import GenericException
from .setup import Setup
from .notification import Notification
from .dispatcher import TaskDispatcher
from .configuration import Configuration
import sys


@click.command("koji-rebuild")
@click.argument(
    "configfile", type=click.Path(exists=True, dir_okay=False, resolve_path=True)
)
def main(configfile):
    """
    CONFIGFILE: YAML formatted configuration file
    """
    logger = logging.getLogger("koji-rebuild")
    setup = Setup(configfile)
    settings = Configuration().settings
    upstream = KojiSession("upstream")
    downstream = KojiSession("downstream")
    notification = Notification()

    packagelist = setup.packagelist()

    if not any(packagelist):
        print("Package list is empty!")
        sys.exit(1)

    msg = str()
    try:
        asyncio.run(TaskDispatcher(upstream, downstream, packagelist).start())
    except KeyboardInterrupt:
        msg = "Received SIGINT"
        logger.exception(msg)
    except GenericException as e:
        msg = e.__str__()
    else:
        msg = "Check attached logs"
    finally:
        alert = settings["notifications"]["alert"]
        if alert.lower() in ["deferred", "prompt"]:
            logs = settings["logging"]
            app = logs["application"]
            completed = logs["completed"]
            failed = logs["failed"]
            asyncio.run(
                notification.send_email(
                    "Koji Build System: Finished",
                    msg,
                    attachment=[app, completed, failed],
                )
            )
        print(msg)


if __name__ == "__main__":
    main()
