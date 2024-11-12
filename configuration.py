import os
import aiosmtplib
import yaml
from util import resolvepath, error
from getpass import getpass
import keyring
from email_validator import validate_email, EmailNotValidError


class Configuration:
    def __init__(self, configfile) -> None:
        configfile = os.path.expanduser(configfile)
        with open(configfile, "r") as f:
            self.parameters = yaml.safe_load(f)

    def get_koji_instance(self, name):
        return self.parameters["instance"][name]

    async def __email_setup(self):
        try:
            os.environ["MAIL_NOTIFY"] = str(self.parameters["email"]["notify"])
        except KeyError:
            os.environ["MAIL_NOTIFY"] = "False"

        if os.environ["MAIL_NOTIFY"] == "True":
            try:
                os.environ["MAIL_TRIGGER"] = str(self.parameters["email"]["trigger"])
                os.environ["MAIL_SERVER"] = str(self.parameters["email"]["server"])
                os.environ["MAIL_USERID"] = str(self.parameters["email"]["sender_id"])
            except:
                error("Email parameters not set")  # TODO

            try:
                validate_email(str(os.getenv("MAIL_USERID")))
            except EmailNotValidError:
                error("Email ID: %s is invalid" % os.getenv("MAIL_USERID"))

            try:
                os.environ["MAIL_PORT"] = str(self.parameters["email"]["port"])
            except KeyError:
                os.environ["MAIL_PORT"] = "587"  # default to 587

            auth = "none"
            try:
                os.environ["MAIL_AUTH"] = str(self.parameters["email"]["auth"])
            except KeyError:
                os.environ["MAIL_AUTH"] = "None"
            else:
                valid_auth = ["tls", "start_tls"]
                auth = os.environ["MAIL_AUTH"]
                if auth.lower() not in valid_auth:
                    os.environ["MAIL_AUTH"] = "None"

            if os.getenv("MAIL_AUTH") != "None":
                service = "kojibuild"
                user = str(os.getenv("USER"))

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
                    print("Successfully authenticated to email server")

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
            pass

        await self.__email_setup()
