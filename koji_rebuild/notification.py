from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import aiosmtplib
import os
import keyring
from .rebuild import BuildState
from .configuration import Configuration
from .util import error


class Notification:

    def __init__(self) -> None:
        try:
            self.notif = Configuration().settings["notifications"]
        except AttributeError:
            error("Configuration not initialized")
        except KeyError:
            self.notif = {}
            return

        self.trigger = self.notif["trigger"]

        email = self.notif["email"]

        self.senderid = email["sender_id"]
        self.recipients = email["recipients"]

        self.server = email["server"]

        self.port = email["port"]
        auth = email["auth"]

        tls = True if auth == "tls" else False
        start_tls = True if (auth == "start_tls" or auth == "starttls") else False

        self.client = aiosmtplib.SMTP(
            hostname=self.server,
            port=self.port,
            username=self.senderid,
            password=keyring.get_password("kojibuild", "kojibuild"),
            use_tls=tls,
            start_tls=start_tls,
        )

    async def send_email(self, subject: str, msg: str, attachment: list | None = None):
        try:
            assert any(self.notif)
        except AssertionError:
            return

        message = MIMEMultipart()
        message["From"] = str(self.senderid)
        message["To"] = self.recipients
        message["Subject"] = subject

        message.attach(MIMEText(msg, "html", "utf-8"))

        if attachment is not None:
            for att in attachment:
                with open(att, "rb") as f:
                    part = MIMEApplication(f.read())
                part["Content-Disposition"] = (
                    'attachment; filename="%s"' % os.path.basename(att)
                )
                message.attach(part)

        await self.client.connect()
        await self.client.send_message(message)
        await self.client.quit()

    async def build_notify(self, pkg, pkg_status, task_url=None):
        try:
            assert any(self.notif)
        except AssertionError:
            return None

        def html_message(msg):
            template = f"<html><b><p>{msg}</p></b></html>"
            return template

        status = "FAILED" if pkg_status == BuildState.FAILED else "COMPLETED"

        subj = "Koji Build System Status: %s" % (status)

        msg = f"Package {pkg} build {status}. "

        if task_url is not None:
            msg += f"Logs available at <b><a href={task_url}>{task_url}</a>"

        msg = html_message(msg)

        if self.trigger == "fail":
            flag = 1 if pkg_status == BuildState.FAILED else 0
        elif self.trigger == "build":
            flag = 1 if pkg_status == BuildState.COMPLETE else 0
        elif self.trigger == "all":
            flag = 1 if pkg_status == (BuildState.COMPLETE or BuildState.FAILED) else 0
        else:
            flag = 0

        if flag:
            await self.send_email(subj, msg)
