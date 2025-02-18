import os
import sys
import yaml
import logging
import aiosmtplib

import keyring
from getpass import getpass

from .session import KojiSession
from .notification import Notification
from .util import error, resolvepath
from email_validator import validate_email, EmailNotValidError
from datetime import datetime


class Configuration:
    mail = dict()
    service = "kojibuild"
    user = "kojibuild"

    def __init__(self, configfile) -> None:
        configfile = os.path.expanduser(configfile)
        with open(configfile, "r") as f:
            self.parameters = yaml.safe_load(f)

    def _email_setup(self):
        try:
            self.notify = self.parameters["notifications"]["notify"]
        except KeyError:
            self.notify = False
            print("Email notifications are turned off")
            return
        else:
            if self.notify is False:
                return

            try:
                self.mail["trigger"] = str(self.parameters["notifications"]["trigger"])
                self.mail["server"] = str(self.parameters["notifications"]["server"])
                self.mail["userid"] = str(self.parameters["notifications"]["sender_id"])
            except KeyError as e:
                print(f"Email parameter(s) undefined: {e}")
                sys.exit(1)

            try:
                validate_email(self.mail["userid"])
            except EmailNotValidError:
                print(f"Email ID: {self.mail["userid"]} is invalid")
                sys.exit(1)

            try:
                self.mail["port"] = self.parameters["notifications"]["port"]
            except KeyError:
                self.mail["port"] = 587

            try:
                self.mail["auth"] = str(self.parameters["notifications"]["auth"])
            except KeyError:
                self.mail["auth"] = None
            finally:
                print(f"mail auth = {self.mail["auth"]}")
                if self.mail["auth"] is not None:
                    valid_auth = ["tls", "start_tls", "starttls"]
                    if self.mail["auth"].lower() not in valid_auth:  # type: ignore
                        print(f'Invalid authentication method "{self.mail["auth"]}"')
                        self.mail_auth = None
                        print("Email authentication set to None")
            # Save password in keyring
            keyring.set_password(
                self.service,
                self.user,
                password=getpass("Enter password for %s :" % (self.mail["userid"])),
            )

    def _get_file(self, attribute: str, default: str | None):
        try:
            f = resolvepath(self.parameters["files"][attribute])
        except KeyError:
            f = "/".join([os.getcwd(), default]) if (default is not None) else None

        return os.path.expanduser(f) if (f is not None) else None

    def _set_pkg_imports(self):
        try:
            attempt = str(self.parameters["pkg_import"]["attempt"])
            self.pkgimport = (
                True if (attempt.lower() == "true" or attempt.lower == "yes") else False
            )
            if self.pkgimport:
                os.environ["FAST_TRACK"] = "1"
        except KeyError:
            self.pkgimport = False

        if self.pkgimport:
            try:
                os.environ["IMPORT_TOPURL"] = str(
                    self.parameters["pkg_import"]["topurl"]
                )
                os.environ["IMPORT_DIR"] = str(
                    resolvepath(self.parameters["pkg_import"]["dir"])
                )
            except KeyError:
                print("Package imports are turned on but attributes undefined")
                sys.exit(1)

    def setup(self):
        try:
            os.environ["MAX_TASKS"] = self.parameters["max_tasks"]
        except KeyError:
            pass
        self._set_pkg_imports()

        self.ignorefile = self._get_file("ignorelist", None)
        self.buildfile = self._get_file("buildlist", "buildlist.txt")
        self.logfile = self._get_file("logfile", "kojibuild.log")

        self._email_setup()


class Setup(Configuration):
    def __init__(self, configfile) -> None:
        super().__init__(configfile)
        self.logger = logging.getLogger("setup")
        self.setup()

    def setup_logger(self, append_date: bool = False):
        assert self.logfile is not None
        if append_date:
            dt = datetime.now()
            dt = dt.strftime("%Y-%m-%d-%H:%M:%S")
            idx = self.logfile.find(".")
            self.logfile = "%s-%s%s" % (self.logfile[:idx], dt, self.logfile[idx:])

        logging.basicConfig(
            filename=self.logfile,
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s : %(message)s",
        )
        return self.logfile

    def get_koji_session(self, name: str):
        try:
            instance = self.parameters["instance"][name]
        except KeyError:
            sys.stderr.write(f"Instance {name} undefined in configuration file!")
            sys.exit(1)
        session = KojiSession(instance)
        return session

    def _get_ignorelist(self):
        ignorelist = None

        if self.ignorefile is not None:
            try:
                with open(self.ignorefile) as f:
                    ignorelist = f.readlines()
            except (FileNotFoundError, EnvironmentError):
                ignorelist = None
                self.logger.warning("Ignorelist could not be fetched!")
        return ignorelist

    def _get_buildlist(self):
        buildlist = list()
        if self.buildfile is not None:
            try:
                with open(self.buildfile) as f:
                    buildlist = f.readlines()
            except FileNotFoundError:
                error("Buildlist could not be fetched!")
        else:
            error("Buildlist was not specified!")

        return buildlist

    def get_packagelist(self):
        ignorelist = self._get_ignorelist()
        buildlist = self._get_buildlist()
        if ignorelist:
            for pkg in ignorelist:
                if pkg in buildlist:
                    buildlist.remove(pkg)

        packagelist = [pkg.strip() for pkg in buildlist]
        return packagelist

    async def _test_smtp_connection(self):
        tls = True if self.mail["auth"] == "tls" else False
        start_tls = True if self.mail["auth"] == "start_tls" else False

        client = aiosmtplib.SMTP(
            hostname=str(self.mail["server"]),
            port=int(self.mail["port"]),  # type: ignore
            username=str(self.mail["userid"]),
            password=keyring.get_password(self.service, self.user),
            use_tls=tls,
            start_tls=start_tls,
        )

        try:
            await client.connect()
        except aiosmtplib.errors.SMTPAuthenticationError:
            print(
                "Authentication error while estabilishing connection with SMTP server"
            )
            sys.exit(1)
        else:
            print("Successfully authenticated to email server")

    def setup_notifications(self) -> Notification | None:
        if self.notify is True:
            recipients = self.parameters["notifications"]["recipients"]
            if not any(recipients):
                self.logger.warning(
                    "Email notifications turned on but no recipients specified! Notifications will be turned off"
                )
                notify = None
            else:
                for mailid in recipients:
                    try:
                        print(f"Validating email id : {mailid}")
                        validate_email(mailid)
                    except EmailNotValidError:
                        error(f"Invalid email address {mailid}")
                subs = ", ".join(recipients)
                notify = Notification(
                    self.mail["server"],
                    self.mail["port"],
                    self.mail["auth"],
                    self.mail["userid"],
                    self.mail["trigger"],
                    subs,
                )
        else:
            notify = None
        return notify
