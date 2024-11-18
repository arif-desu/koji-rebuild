from email.mime.text import MIMEText
import aiosmtplib
import os
import keyring
from rebuild import BuildState


class Notification:

    def __init__(self, recipients: str) -> None:
        self.recipients = recipients
        self.senderid = str(os.getenv("MAIL_USERID"))
        self.trigger = os.getenv("MAIL_TRIGGER")

        tls = True if os.getenv("MAIL_AUTH") == "tls" else False
        start_tls = True if os.getenv("MAIL_AUTH") == "start_tls" else False

        self.client = aiosmtplib.SMTP(
            hostname=str(os.getenv(("MAIL_SERVER"))),
            port=int(os.getenv("MAIL_PORT")),  # type:ignore
            username=str(os.getenv("MAIL_USERID")),
            password=keyring.get_password("kojibuild", str(os.getenv("USER"))),
            use_tls=tls,
            start_tls=start_tls,
        )

    async def send_email(self, subject: str, msg: str):
        message = MIMEText(msg, "html", "utf-8")
        message["From"] = str(self.senderid)
        message["To"] = self.recipients
        message["Subject"] = subject

        await self.client.connect()
        await self.client.send_message(message)
        await self.client.quit()

    async def build_notify(self, pkg_status, task_url):
        if task_url is None:
            return
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
