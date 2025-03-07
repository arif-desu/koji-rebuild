import os
import sys
import logging
import aiosmtplib
import asyncio
import keyring
from getpass import getpass

from .util import resolvepath
from .configuration import Configuration
from email_validator import validate_email, EmailNotValidError


class Setup:
    email = dict()
    service = "kojibuild"
    user = "kojibuild"
    logger = logging.getLogger("Setup")

    def __init__(self, configfile: str) -> None:
        try:
            self.settings = Configuration(configfile).settings
        except FileNotFoundError:
            print(f"Configuration file {configfile} not found!")
            sys.exit(1)

        self._logging()
        self._pkg_build_params()
        self._email_params()

        if self.settings["notifications"]["alert"] != "off":
            event_loop = asyncio.get_event_loop()
            event_loop.run_until_complete(self.test_smtp_connection())

    def _set_defaults(self, default: dict, user: dict):
        for key in default:
            if key not in user:
                user[key] = default[key]

    def _pkg_build_params(self):
        defaults = {
            "max_tasks": 10,
            "buildlist": f"{os.getcwd()}/build.list",
            "ignorelist": f"{os.getcwd()}/ignore.list",
            "fasttrack": False,
            "topurl": "https://kojipkgs.fedoraproject.org/packages",
            "download_dir": f"{os.path.expanduser('~')}/.rpms",
        }

        if "package_builds" not in self.settings:
            self.settings["package_builds"] = defaults

        pkgbuilds = self.settings["package_builds"]

        for key in ["buildlist", "ignorelist", "download_dir"]:
            pkgbuilds[key] = resolvepath(pkgbuilds[key])

        self._set_defaults(defaults, pkgbuilds)

    def _logging(self):
        defaults = {
            "application": f"{os.getcwd()}/kojibuild.log",
            "completed": f"{os.getcwd()}/completed.list",
            "failed": f"{os.getcwd()}/failed.list",
        }

        if "logging" not in self.settings:
            self.settings["logging"] = defaults

        logfile = self.settings["logging"]

        for key in logfile:
            logfile[key] = resolvepath(logfile[key])

        self._set_defaults(defaults, logfile)

        logging.basicConfig(
            filename=logfile["application"],
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s : %(message)s",
        )

    def packagelist(self):
        def ftol(filename, default: str | None = None):
            try:
                fp = resolvepath(self.settings["package_builds"][filename])
            except KeyError:
                fp = "/".join([os.getcwd(), default]) if default else None

            fp = os.path.expanduser(fp) if fp else None

            if fp:
                try:
                    with open(fp) as f:
                        return f.readlines()
                except FileNotFoundError:
                    self.logger.info(f"File {fp} not found!")
                    return []
            else:
                return []

        buildlist = ftol(
            self.settings["package_builds"]["buildlist"], default="build.list"
        )
        ignorelist = ftol(
            self.settings["package_builds"]["ignorelist"], default="ignore.list"
        )

        try:
            assert any(buildlist)
        except AssertionError:
            print("Buildlist is empty!")
            sys.exit(1)

        if any(ignorelist):
            for pkg in ignorelist:
                if pkg in buildlist:
                    buildlist.remove(pkg)

        pkglist = [pkg.strip() for pkg in buildlist]
        return pkglist

    def _email_params(self):

        defaults = {
            "alert": "off",
            "trigger": "fail",
            "email": {
                "server": "smtp.example.com",
                "port": 587,
                "auth": "none",
                "sender_id": "kojiuser@example.com",
                "recipients": [],
            },
        }

        if "notifications" not in self.settings:
            self.settings["notifications"] = {}
            self.logger.info("Notifications are turned off")
            return

        notif = self.settings["notifications"]

        self._set_defaults(defaults, notif)

        email = notif["email"]
        try:
            validate_email(email["sender_id"])
        except EmailNotValidError:
            print(f"Email ID: {email["sender_id"]} is invalid")
            sys.exit(1)

        if not (isinstance(email["recipients"], list) or any(email["recipients"])):
            print("Please specify recipients in as a list")
            sys.exit(1)
        else:
            for id in email["recipients"]:
                try:
                    validate_email(id)
                except EmailNotValidError:
                    print(f"{id} is not a valid email address")
                    sys.exit(1)

        valid_auth = ["none", "tls", "start_tls", "starttls"]
        auth = email["auth"]

        if auth.lower() not in valid_auth:
            print(f"Invalid authentication method {auth}")
            sys.exit(1)

    async def test_smtp_connection(self):
        password = keyring.get_password(self.service, self.user)
        email = self.settings["notifications"]["email"]
        tls = True if email["auth"] == "tls" else False
        start_tls = True if email["auth"] == "start_tls" else False
        test = False

        if password is None:
            flag = 0
            for _ in range(3):
                password = getpass(f"Enter password for {self.email["userid"]}")

                client = aiosmtplib.SMTP(
                    hostname=email["server"],
                    port=email["port"],
                    username=email["userid"],
                    password=password,
                    use_tls=tls,
                    start_tls=start_tls,
                )

                try:
                    test = await client.connect()
                except aiosmtplib.errors.SMTPAuthenticationError:
                    print(
                        "Authentication error while estabilishing connection with SMTP server"
                    )
                    continue
                else:
                    print("Successfully authenticated to email server")
                    break

            if test is False:
                print("Invalid password. Try again!")
            else:
                print("Successfully authenticated to SMTP server")
                flag = 1

            if flag == 0:
                print(
                    "Maximum number of attempts reached. Please check email parameters in configfile"
                )
                sys.exit(1)

        assert password is not None
        keyring.set_password(self.service, self.user, password=password)

        return True
