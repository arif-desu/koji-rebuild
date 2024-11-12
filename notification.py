from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib
import os
import keyring
from rebuild import BuildState


class Notification:

    def __init__(self, recipients: str) -> None:
        self.recipients = recipients
        self.senderid = os.getenv("MAIL_USERID")
        self.trigger = os.getenv("MAIL_TRIGGER")
        self.server = str(os.getenv("MAIL_SERVER"))
        self.port = int(os.getenv("MAIL_PORT"))  # type:ignore

    async def send_email(self, subject: str, msg: str):
        message = MIMEMultipart("alternative")
        message["From"] = str(self.senderid)
        message["To"] = self.recipients
        message["Subject"] = subject

        html_msg = MIMEText(msg, "html", "utf-8")
        message.attach(html_msg)

        service = "kojibuild"
        user = str(os.getenv("USER"))

        await aiosmtplib.send(
            message=message,
            hostname=self.server,
            port=self.port,  # type: ignore
            start_tls=True,
            username=self.senderid,
            password=keyring.get_password(service_name=service, username=user),
        )

    async def build_notify(self, pkg_status, task_url):
        subj = "Koji Build System : "
        subj += "FAILED" if pkg_status == BuildState.FAILED else "COMPLETED"
        msg = f"<html><b><p>Check logs at <a href={task_url}>{task_url}</a></p></b></html>"
        trigger = os.getenv("MAIL_TRIGGER")

        if trigger == "fail":
            flag = 1 if pkg_status == BuildState.FAILED else 0
        elif trigger == "build":
            flag = 1 if pkg_status == BuildState.COMPLETE else 0
        elif trigger == "all":
            flag = 1 if pkg_status == (BuildState.COMPLETE or BuildState.FAILED) else 0
        else:
            flag = 0

        if flag:
            await self.send_email(subj, msg)
