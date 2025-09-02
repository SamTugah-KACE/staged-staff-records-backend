import asyncio
import os
from fastapi import BackgroundTasks
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from jinja2 import Template
from typing import List, Optional
from Utils.email_utils import parse_html_from_template
from Utils.config import *
import string
import random
from Utils.util import get_organization_acronym

settings = DevelopmentConfig()

# Email configuration (using environment variables for security)
conf = ConnectionConfig(
    # MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    # MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    # MAIL_FROM=EmailStr(os.getenv("MAIL_FROM")),
    # MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    # MAIL_SERVER=os.getenv("MAIL_SERVER"),
    # MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS"),
    # USE_CREDENTIALS=os.getenv("USE_CREDENTIALS")

    

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

# Define the email service
class EmailService:
    def __init__(self):
        self.mail = FastMail(conf)

    # def send_email_with_template_sync(self, recipients, subject, template_name, template_data):
    #     # Call the async function synchronously
    #     asyncio.run(self.send_email_with_template(None, recipients, subject, template_name, template_data))
    
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
    
    # Define the email template
    # def get_email_template(username: str, password: str, href: str) -> str:
    #     return f"""
    #     <h2>GI-KACE Staff Records System</h2>
    #     <p>Your account has been created successfully. Below are your login credentials:</p>
    #     <p><strong>Username:</strong> {username}</p>
    #     <p><strong>Password:</strong> {password}</p>
    #     <p>Please change your password after logging in for the first time using the link: <a href='{href}'>Login</a></p>
    #     """

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
        background_tasks.add_task(self.mail.send_message, message)

    async def send_plain_text_email(self, background_tasks: BackgroundTasks, recipients: List[EmailStr], subject: str, body: str):
        await self.send_email(background_tasks, recipients, subject, body=body)

    async def send_html_email(self, background_tasks: BackgroundTasks, recipients: List[EmailStr], subject: str, html_body: str):
        await self.send_email(background_tasks, recipients, subject, html_body=html_body)

    async def send_email_with_template(self, background_tasks: BackgroundTasks, recipients: List[EmailStr], subject: str, template_name: str, template_data: dict):
        await self.send_email(background_tasks, recipients, subject, template_name=template_name, template_data=template_data)

    # Define the email template
def get_email_template(username: str, password: str, href: str, org_name:str=None) -> str:
    print("\n\norg_name in email_template:: ", org_name)
    name = None
    if org_name is None:
        name = "GI-KACE"
    else:
        name = get_organization_acronym(org_name)
        

    print("\nname:: ", name)
    return f"""
    <h2>{name} <br/>Staff Records System</h2>
    <p>Your account has been created successfully. Below are your login credentials:</p>
    <p><strong>Username:</strong> {username}</p>
    <p><strong>Password:</strong> {password}</p>
    <p>Please change your password after logging in for the first time using the link: <a href='{href}'>Login</a></p>
    """

def account_emergency() -> str:
    return """
    <h2>GI-KACE Staff Records System</h2>
    <p>Your account has been <strong>disabled</strong> due to multiple intrusion attempts.</p>
    <p>Please contact the System's Administrator for redress.</p>

    <p>Thank you.</p>
    """
 