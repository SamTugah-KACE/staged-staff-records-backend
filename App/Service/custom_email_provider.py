"""
Email Service Module
Supports two multi-tenant application models:

 1. App1: Schema-per-tenant (each org has its own schema)
 2. App2: Shared public schema (single DB/schema); uses UUID4

Drop this file into `services/email_service.py`, instantiate with `schema_based=True` for App1 or `schema_based=False` for App2.
"""
from abc import ABC, abstractmethod
import smtplib
import httpx
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import sendgrid
from sendgrid.helpers.mail import Mail
import ssl



# ---------- Provider Interfaces and Implementations ----------
class EmailProvider(ABC):
    @abstractmethod
    def send_message(self, msg: MIMEMultipart) -> None:
        pass

    @abstractmethod
    def test_connection(self) -> None:
        pass

class SMTPProvider(EmailProvider):
    def __init__(self, host: str, port: int, username: str, password: str, use_tls: bool = True):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.context = ssl.create_default_context()

    def _get_connection(self):
        if self.host == "smtp.sendgrid.net":
            server = smtplib.SMTP(self.host, self.port, timeout=60)
            server.ehlo()
            if self.use_tls:
                server.starttls(context=self.context)
                server.ehlo()
            return server
        elif self.port == 465:
            return smtplib.SMTP_SSL(self.host, self.port, context=self.context, timeout=60)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=60)
            server.ehlo()
            if self.use_tls:
                server.starttls(context=self.context)
                server.ehlo()
            return server

    def test_connection(self):
        with self._get_connection() as server:
            login_user = "apikey" if self.host == "smtp.sendgrid.net" else self.username
            server.login(login_user, self.password)

    def send_message(self, msg):
        with self._get_connection() as server:
            login_user = "apikey" if self.host == "smtp.sendgrid.net" else self.username
            server.login(login_user, self.password)
            server.sendmail(msg["From"], msg["To"].split(","), msg.as_string())

class SendGridProvider(EmailProvider):
    def __init__(self, api_key):
        self.sg = sendgrid.SendGridAPIClient(api_key)

    def test_connection(self):
        # Simple call to ensure credentials work
        response = self.sg.client.user.profile.get()
        if response.status_code >= 400:
            raise ConnectionError(f"SendGrid error: {response.status_code} - {response.body}")

    def send_message(self, msg: MIMEMultipart):
        # ✅ Properly extract HTML content from MIME message
        html_content = None
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/html':
                html_content = part.get_payload(decode=True).decode(errors='replace')
                break

        if not html_content:
            raise ValueError("No HTML content found in email message.")

        mail = Mail(
            from_email=msg['From'],
            to_emails=[r.strip() for r in msg['To'].split(',')],
            subject=msg['Subject'],
            html_content=html_content
        )

        response = self.sg.send(mail)
        if response.status_code >= 400:
            raise RuntimeError(f"SendGrid send failed: {response.status_code} - {response.body}")


def get_provider(cfg):
    if cfg.provider == "sendgrid":
        return SendGridProvider(cfg.api_key)
    elif cfg.provider in ["smtp", "gmail", "yahoo", "outlook"]:
        return SMTPProvider(cfg.host, cfg.port, cfg.username, cfg.password, cfg.use_tls)
    raise ValueError(f"Unsupported email provider: {cfg.provider}")