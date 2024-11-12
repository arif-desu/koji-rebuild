from email.message import EmailMessage
import aiosmtplib
import os
import keyring
from rebuild import BuildState


class Notification:

    def __init__(self, recipients: list) -> None:
        self.recipients = recipients
        self.senderid = os.getenv("MAIL_USERID")
        self.trigger = os.getenv("MAIL_TRIGGER")
        self.server = str(os.getenv("MAIL_SERVER"))
        self.port = int(os.getenv("MAIL_PORT"))  # type:ignore

    async def send_email(self, subject: str, msg: str):
        message = EmailMessage()
        message["From"] = self.senderid
        message["To"] = self.recipients
        message["Subject"] = subject
        message.set_content(msg)

        service = "kojibuild"
        user = str(os.getenv("USER"))

        await aiosmtplib.send(
            message=message,
            hostname=self.server,
            port=self.port,  # type: ignore
            start_tls=True,
            username=str(os.getenv("MAIL_USERID")),
            password=keyring.get_password(service_name=service, username=user),
        )

    # TODO: Check notification trigger
    async def build_notify(self, pkg_status, taskurl):
        subj = "Koji Build System : "
        subj += "FAILED" if pkg_status == BuildState.FAILED else "COMPLETED"
        msg = f"Check logs at {taskurl}"

        await self.send_email(subj, msg)
