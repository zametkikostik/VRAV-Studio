"""Email delivery abstraction: console | smtp | resend."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("vrav.email")


class EmailProvider(Protocol):
    async def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None: ...


class ConsoleEmailProvider:
    async def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None:
        logger.info("EMAIL console to=%s subject=%s body=%s", to, subject, text[:500])


class SMTPEmailProvider:
    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST", "localhost")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.from_addr = os.getenv("EMAIL_FROM", "noreply@vrav.local")
        self.use_tls = os.getenv("SMTP_TLS", "1") not in ("0", "false", "False")

    async def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)


class ResendEmailProvider:
    def __init__(self) -> None:
        self.api_key = os.getenv("RESEND_API_KEY", "")
        self.from_addr = os.getenv("EMAIL_FROM", "noreply@vrav.local")
        if not self.api_key:
            raise RuntimeError("RESEND_API_KEY required")

    async def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None:
        import httpx

        payload = {"from": self.from_addr, "to": [to], "subject": subject, "text": text}
        if html:
            payload["html"] = html
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()


def get_email_provider() -> EmailProvider:
    name = os.getenv("EMAIL_PROVIDER", "console").lower()
    if name == "smtp":
        return SMTPEmailProvider()
    if name == "resend":
        return ResendEmailProvider()
    return ConsoleEmailProvider()
