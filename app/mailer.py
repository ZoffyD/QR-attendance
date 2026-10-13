"""Sends forgot-password codes to teachers and the admin. Without SMTP settings the code is printed in the
server console, so the system still works on a school LAN with no email."""
import logging
import smtplib
from email.message import EmailMessage

from . import config

log = logging.getLogger("attendance.mail")


def send_reset_code(to: str, name: str, username: str, code: str) -> None:
    if not config.SMTP_HOST or not to:
        print(f"[attendance] Password reset code for {name} ({username}): {code}", flush=True)
        return
    msg = EmailMessage()
    msg["Subject"] = "Your QR Attendance password reset code"
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg.set_content(f"Hello {name},\n\nYour password reset code is: {code}\n\nEnter it on the Forgot password page "
                    f"together with your username ({username}). It works once, for {config.RESET_MINUTES} minutes.\n\n"
                    "If you did not ask for this, ignore this email.\n")
    try:
        cls = smtplib.SMTP_SSL if config.SMTP_SSL else smtplib.SMTP
        with cls(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
            if not config.SMTP_SSL:
                s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)
    except Exception as exc:   # never reveal mail problems to the person asking; log them for the admin
        log.warning("could not send reset email to %s: %s", to, exc)
        print(f"[attendance] Email failed. Reset code for {name} ({username}): {code}", flush=True)
