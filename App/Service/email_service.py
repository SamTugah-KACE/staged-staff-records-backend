import asyncio
import logging
import os
from fastapi import BackgroundTasks
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from jinja2 import Template
from typing import List, Optional
from Models.Tenants.organization import Organization
from Utils.util import get_organization_acronym
from Utils.email_utils import parse_html_from_template
from Utils.config import *
import string
import random
from tenacity import retry, stop_after_attempt, wait_exponential

settings = ProductionConfig()


# Email configuration (using environment variables for security)
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,  
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS
)

mailer = FastMail(conf)
logger = logging.getLogger("email_service")

# Define the email service
class EmailService:
    def __init__(self):
        self.mail = FastMail(conf)

    
    @staticmethod
    @retry(
        stop=stop_after_attempt(settings.EMAIL_RETRY_ATTEMPTS),
        # either exponential back‑off…
        wait=wait_exponential(
            multiplier=settings.EMAIL_RETRY_DELAY,
            min=settings.EMAIL_RETRY_DELAY,
            max=settings.EMAIL_RETRY_DELAY * 10,
        ),
        # …or, if you want a fixed pause between retries, use:
        # wait=wait_fixed(settings.EMAIL_RETRY_DELAY),
        reraise=True,
    )
    async def _actually_send(message: MessageSchema):
        """
        Retry‑wrapped actual send.
        Internal helper: retries on failure according to config.
        """
        await mailer.send_message(message)

    
    @staticmethod
    async def send_html(recipients: list[str], subject: str, html_body: str):
        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            body=html_body,
            subtype="html"
        )
        await mailer.send_message(message)

    
    # Utility functions
    def generate_username(first_name: str, surname: str) -> str:
        print("\nGenerated Username: ", f"{first_name.lower()}.{surname.lower()}{random.randint(100, 999)}")
        return f"{first_name.lower()}.{surname.lower()}{random.randint(100, 999)}"
    
    def generate_password(length: int = 6) -> str:
        #characters = string.ascii_letters + string.digits + string.punctuation
        characters = string.ascii_letters + string.digits
        print("\n----------------in password-------\n--------------------------------------------------------\ncharacters: ", characters)
        print("\nGenerated Password: ", ''.join(random.choice(characters) for _ in range(length)))
        return ''.join(random.choice(characters) for _ in range(length))
    
    
    def account_emergency() -> str:
        return """
        <h2>GI-KACE Staff Records System</h2>
        <p>Your account has been <strong>disabled</strong> due to multiple intrusion attempts.</p>
        <p>Please contact the System's Administrator for redress.</p>

        <p>Thank you.</p>
        """

    def send_email_with_template_sync(self, recipients, subject, template_name, template_data):
        # Call the async function synchronously
        asyncio.run(self.send_email_with_template(None, recipients, subject, template_name, template_data))

    
    def send_html_email_sync(self, recipients, subject, html_body):
        asyncio.run(self.send_html_email(None, recipients, subject, html_body))

    def send_plain_text_email_sync(self, recipients, subject, body):
        asyncio.run(self.send_plain_text_email(None, recipients, subject, body))

        
    async def send_email(
        self,
        background_tasks: BackgroundTasks,
        recipients: List[EmailStr],
        subject: str,
        body: str = None,
        html_body: str = None,
        template_name: Optional[str] = None,
        template_data: Optional[dict] = None
    ):
        """
        Send an email either as text or HTML. Optionally, use a template with dynamic content.
        """
        if template_name:
            # Parse the template file
            template_body = parse_html_from_template(template_name, template_data)
        elif html_body:
            # If no template, but HTML body is provided
            template_body = html_body
        else:
            # Send a plain text email if body is given
            template_body = body

        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            body=template_body if html_body or template_name else body,
            subtype="html" if html_body or template_name else "plain",
        )

        # Send the email asynchronously
        # background_tasks.add_task(self.mail.send_message, message)
        # schedule the retry‑wrapped send in background
        background_tasks.add_task(self._send_with_logging, message)

    async def _send_with_logging(self, message: MessageSchema):
        try:
            await self._actually_send(message)
            logger.info("Email sent ✓ to %s", message.recipients)
            logger.info("Email sent to %s: %s", message.recipients, message.subject)
        except Exception as exc:
            # Log full traceback—but don’t re‑raise, so it won’t crash the request.
            logger.error("Failed to send email to %s: %s", message.recipients, exc, exc_info=True)

    async def send_plain_text_email(self, background_tasks: BackgroundTasks, recipients: List[EmailStr], subject: str, body: str):
        await self.send_email(background_tasks, recipients, subject, body=body)

    async def send_html_email(self, background_tasks: BackgroundTasks, recipients: List[EmailStr], subject: str, html_body: str):
        await self.send_email(background_tasks, recipients, subject, html_body=html_body)

    async def send_email_with_template(self, background_tasks: BackgroundTasks, recipients: List[EmailStr], subject: str, template_name: str, template_data: dict):
        await self.send_email(background_tasks, recipients, subject, template_name=template_name, template_data=template_data)

    # Define the email template
# Define the email template
def get_email_template(username: str, password: str, href: str, org_name:str=None, org_logo:str=None) -> str:
    print("\n\norg_name in email_template:: ", org_name)
    name = None
    if org_name is None:
        name = "GI-KACE"
    else:
        name = get_organization_acronym(org_name)
        

    print("\nname:: ", name)
    # return f"""
    # <h2>{name} Staff Records System</h2>
    # <p>Your account has been created successfully. Below are your login credentials:</p>
    # <p><strong>Username:</strong> {username}</p>
    # <p><strong>Password:</strong> {password}</p>
    # <p>Please change your password after logging in for the first time using the link: <a href='{href}'>Login</a></p>
    # """
    return f"""
    <div style="max-width:600px;margin:0 auto;font-family:Arial,sans-serif;">
        <div style="text-align:center;padding:20px;">
            <img src="{org_logo}" alt="{name} Logo" style="max-width:200px; width:100%; height:auto;">
        </div>
        <div style="padding:20px;">
            <h2>{name} Staff Records System</h2>
            <p>Dear Staff,</p>
            <p>Your account has been created successfully. 
            <br/>Your username is <strong>{username}</strong>.
            <br/>Your Password is <strong>{password}</strong>
            </p>
            <p>Please change your password upon your first login.</p>
        
            <div style="text-align:center;margin-top:30px;">
             <a href="{href}" style="display:inline-block;padding:10px 20px;background-color:#007bff;color:#fff;text-decoration:none;border-radius:4px;">Login</a> 
            </div>
            <p style="margin-top:30px;">Best regards,<br>{name} Team</p>
        </div>
        </div>
        """

def build_account_email_html(row_data: dict,  logo_url: str, login_href: str, pwd: str) -> str:
        """
        Build a dynamic HTML email template for account creation.
        The logo appears on top responsively, then a personalized salutation, account details, and a styled login button.
        """
        title = row_data.get("title") or ""
        first_name = row_data.get("first_name") or ""
        last_name = row_data.get("last_name") or ""
        email = row_data.get("email") or ""
        org_name = row_data.get("org_name") or "GI-KACE"
        
        org_acronym = get_organization_acronym(org_name)


        html_template = f"""
        <div style="max-width:600px;margin:0 auto;font-family:Arial,sans-serif;">
        <div style="text-align:center;padding:20px;">
            <img src="{logo_url}" alt="{org_acronym} Logo" style="max-width:200px; width:100%; height:auto;">
        </div>
        <div style="padding:20px;">
            <h2>{org_acronym} Staff Records System</h2>
            <p>Dear {title} {first_name},</p>
            <p>Your account has been created successfully. 
            <br/>Your username is <strong>{email}</strong>.
            <br/>Your Password is <strong>{pwd}</strong>
            </p>
            <p>Please change your password upon your first login.</p>
        
            <div style="text-align:center;margin-top:30px;">
             <a href="{login_href}" style="display:inline-block;padding:10px 20px;background-color:#007bff;color:#fff;text-decoration:none;border-radius:4px;">Login</a> 
            </div>
            <p style="margin-top:30px;">Best regards,<br>{org_acronym} Team</p>
        </div>
        </div>
        """
        return html_template

def get_update_notification_email_template(username: str, organization: Organization) -> str:
    """
    Returns an HTML email template for notifying the user about their updated account details.
    If an organization logo URL is available in organization.logos, it is displayed at the top.
    """
    logo_url = ""
    if organization.logos:
        try:
            # Ensure logos is a dict
            logos = organization.logos if isinstance(organization.logos, dict) else json.loads(organization.logos)
            # Try "primary" key; if not found, get first value.
            logo_url = logos.get("primary") or next(iter(logos.values()), "")
        except Exception:
            logo_url = ""
    
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #e0e0e0; padding: 20px;">
          <div style="text-align: center;">
            {"<img src='" + logo_url + "' alt='Organization Logo' style='max-height: 100px;'/>" if logo_url else ""}
          </div>
          <h2 style="color: #007BFF;">Account Update Notification</h2>
          <p>Hello {username},</p>
          <p>Your account details have been updated successfully. If you did not request these changes, please contact your administrator immediately.</p>
          <p>Regards,<br/>The {organization.name} Team</p>
          <hr style="border: none; border-top: 1px solid #e0e0e0;" />
          <p style="font-size: 12px; color: #777;">This email was sent from an automated system. Please do not reply directly.</p>
        </div>
      </body>
    </html>
    """

def account_emergency() -> str:
    return """
    <h2>GI-KACE Staff Records System</h2>
    <p>Your account has been <strong>disabled</strong> due to multiple intrusion attempts.</p>
    <p>Please contact the System's Administrator for redress.</p>

    <p>Thank you.</p>
    """


# Synchronous helper for sending email notifications.
def send_email_notification(recipient: str, subject: str, message: str) -> None:
    try:
        service = EmailService()
        service.send_plain_text_email_sync([recipient], subject, message)
    except Exception as e:
        raise Exception("Failed to send email notification.") from e
 