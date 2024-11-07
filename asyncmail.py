from email.message import EmailMessage
import aiosmtplib
import os


async def send_email(subject: str, recipients: str, msg: str):
    message = EmailMessage()
    message["From"] = str(os.getenv("MAIL_USERID"))
    message["To"] = recipients
    message["Subject"] = subject
    message.set_content(msg)
    print(message)

    await aiosmtplib.send(
        message=message,
        hostname=str(os.getenv("MAIL_SERVER")),
        port=int(os.getenv("MAIL_PORT")),  # type: ignore
        start_tls=True,
        username=str(os.getenv("MAIL_USERID")),
        password=str(os.getenv(("MAIL_PASSWORD"))),
    )
