import os
import aiosmtplib
import yaml
from util import resolvepath, error
from getpass import getpass
import keyring
from email_validator import validate_email, EmailNotValidError
import logging


class Configuration:
    def __init__(self, configfile) -> None:
        configfile = os.path.expanduser(configfile)
        with open(configfile, "r") as f:
            self.parameters = yaml.safe_load(f)

        self.logger = logging.getLogger(__name__)

    def get_koji_instance(self, name):
        return self.parameters["instance"][name]

    async def __email_setup(self):
        try:
            os.environ["MAIL_NOTIFY"] = str(self.parameters["email"]["notify"])
        except KeyError:
            os.environ["MAIL_NOTIFY"] = "False"

        if os.getenv("MAIL_NOTIFY") == "False":
            return 1
        else:
            try:
                os.environ["MAIL_TRIGGER"] = str(self.parameters["email"]["trigger"])
                os.environ["MAIL_SERVER"] = str(self.parameters["email"]["server"])
                os.environ["MAIL_USERID"] = str(self.parameters["email"]["sender_id"])
            except:
                error("Email parameter(s) undefined", exc_info=True)

            try:
                validate_email(str(os.getenv("MAIL_USERID")))
            except EmailNotValidError:
                error("Email ID: %s is invalid" % os.getenv("MAIL_USERID"))

            try:
                os.environ["MAIL_PORT"] = str(self.parameters["email"]["port"])
            except KeyError:
                os.environ["MAIL_PORT"] = "587"  # default to 587

            try:
                auth = str(self.parameters["email"]["auth"])
            except KeyError:
                auth = "none"
            finally:
                valid_auth = ["none", "tls", "start_tls"]
                if auth.lower() not in valid_auth:  # type: ignore
                    self.logger.critical(f'Invalid authentication method "auth"')
                auth = "none"

            service = "kojibuild"
            user = str(os.getenv("USER"))

            # Save password in keyring
            keyring.set_password(
                service,
                user,
                password=getpass(
                    "Enter password for %s :" % (os.getenv("MAIL_USERID"))
                ),
            )

            tls = True if auth == "tls" else False
            start_tls = True if auth == "start_tls" else False

            client = aiosmtplib.SMTP(
                hostname=os.getenv("MAIL_SERVER"),
                port=int(os.getenv("MAIL_PORT")),  # type: ignore
                username=os.getenv("MAIL_USERID"),
                password=keyring.get_password(service, user),
                use_tls=tls,
                start_tls=start_tls,
            )

            try:
                await client.connect()
            except aiosmtplib.errors.SMTPAuthenticationError:
                error("ERROR! Could not authenticate to email server")
            else:
                self.logger.info("Successfully authenticated to email server")

            return 0

    async def setup(self):
        try:
            os.environ["IMPORT_ATTEMPT"] = str(self.parameters["pkg_import"]["attempt"])
        except KeyError:
            os.environ["IMPORT_ATTEMPT"] = "False"

        if os.getenv("IMPORT_ATTEMPT") == "True":
            try:
                os.environ["IMPORT_TOPURL"] = str(
                    self.parameters["pkg_import"]["topurl"]
                )
                os.environ["IMPORT_DIR"] = str(
                    resolvepath(self.parameters["pkg_import"]["dir"])
                )
            except KeyError:
                error(exc_info=True)

        try:
            os.environ["BUILDLIST"] = str(
                resolvepath(self.parameters["files"]["buildlist"])
            )
            os.environ["IGNORELIST"] = str(
                resolvepath(self.parameters["files"]["ignorelist"])
            )
            os.environ["LOGFILE"] = str(
                resolvepath(self.parameters["files"]["logfile"])
            )
        except KeyError:
            pass  # We ignore or set to defaults if not defined

        await self.__email_setup()
