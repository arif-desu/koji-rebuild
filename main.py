import os
import sys
import asyncio
import logging
import typing
from kojisession import KojiSession
from notification import Notification
from util import error
import configuration
from dispatcher import task_dispatcher
from email_validator import validate_email, EmailNotValidError


async def main():
    try:
        configfile = sys.argv[1]
    except IndexError:
        configfile = os.path.expanduser("/".join([os.getcwd(), "config.yml"]))

    config = configuration.Configuration(configfile)

    await config.setup()

    logging.basicConfig(
        filename=os.getenv("LOGFILE", default="kojibuild.log"),
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s : %(message)s",
    )

    logger = logging.getLogger(__name__)

    upstream = KojiSession(config.get_koji_instance("upstream"))
    downstream = KojiSession(config.get_koji_instance("downstream"))

    def fetch_tag(session):
        try:
            tag = session.instance["tag"]
        except KeyError:
            target = session.getBuildTarget(session.instance["target"])
            tag = target["dest_tag_name"]
        return tag

    dest_tag = fetch_tag(downstream)
    upst_tag = fetch_tag(upstream)

    # Check for an ignorelist
    ignorefile: typing.TextIO | None
    ignorelist = list()

    if os.getenv("IGNORELIST") != "None":
        try:
            ignorefile = open(str(os.getenv("IGNORELIST")))
            ignorelist = ignorefile.readlines()
            ignorefile.close()
        except (FileNotFoundError, EnvironmentError):
            ignorefile = ignorelist = None
            logger.warning("Ignorelist was not specified. Bypassing ignore requests")
            pass

    # Check for a buildlist
    buildfile: typing.TextIO
    buildlist: list[str]
    if os.getenv("BUILDLIST") != "None":
        try:
            buildfile = open(str(os.getenv("BUILDLIST")), "r")
        except FileNotFoundError:
            error(f"File {os.getenv('BUILDLIST')} not found!")
    else:
        buildfile = open("buildlist.txt", "r+")
        for pkg in upstream.get_package_list(upst_tag):
            buildfile.write(pkg + "\n")

    buildlist = buildfile.readlines()  # type: ignore
    buildfile.close()  # type: ignore

    # Remove package names from buildlist that are included in ignorelist
    if ignorelist:
        for pkg in ignorelist:
            if pkg in buildlist:
                buildlist.remove(pkg)

    # Create list of packages
    packages = [pkg.strip() for pkg in buildlist]

    # Setup notifications
    if os.getenv("MAIL_NOTIFY") == "True":
        recipients = config.parameters["email"]["recipients"]
        if not any(recipients):
            logger.critical(
                "Email notifications turned on but no recipients specified! Notifications will be turned off"
            )
            notify = None
        else:
            for mail in recipients:
                try:
                    validate_email(mail)
                except EmailNotValidError:
                    error(f"Invalid email address {mail}")
            recipients = ", ".join(recipients)
            notify = Notification(recipients)
    else:
        notify = None

    # Add packages to downstream koji database
    downstream.auth_login()
    for pkg in packages:
        downstream.packageListAdd(
            taginfo=dest_tag, pkginfo=pkg, owner=downstream.getLoggedInUser()["name"]
        )

    await task_dispatcher(upstream, downstream, packages, notify)


if __name__ == "__main__":
    asyncio.run(main())
