
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import json
import logging
import os
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from os import path as _p
from Service.custom_email_provider import EmailProvider, SMTPProvider, SendGridProvider
from Schemas.schemas import TenantEmailSettings

# ---------- Template Renderer ----------
logger = logging.getLogger(__name__)


class TemplateRenderer:
    def __init__(
        self,
        tenant_templates_dir: str,
        global_templates_dir: str = "templates/emails"
    ):
        loaders = []
        if os.path.isdir(tenant_templates_dir):
            loaders.append(FileSystemLoader(tenant_templates_dir))
        if os.path.isdir(global_templates_dir):
            loaders.append(FileSystemLoader(global_templates_dir))
        if not loaders:
            loaders.append(FileSystemLoader("."))  # fallback

        # ✅ FIX: Pass the list of directories, not FileSystemLoader objects
        self.env = Environment(
            loader=FileSystemLoader([ld.searchpath[0] for ld in loaders if hasattr(ld, 'searchpath')]),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # 🔁 Search paths: tenant → global → codebase fallback
        # self.template_paths = [
        #     tenant_templates_dir,
        #     global_templates_dir,
        #     os.path.abspath("app/templates")  # ✅ fallback to project root templates
        # ]

        # self.env = Environment(
        #     loader=FileSystemLoader(self.template_paths),
        #     autoescape=select_autoescape(['html', 'xml'])
        # )

    def render(self, template_name: str, context: dict) -> str:
        if not template_name:
            # No template requested → inline
            return self._inline(context)
        try:
            tmpl = self.env.get_template(template_name)
            return tmpl.render(**context)
        except (TemplateNotFound, Exception) as e:
            # ✅ Dynamically determine the full fallback path
            base_dir = os.path.dirname(os.path.abspath(__file__))  # resolves to /App/Service
            fallback_path = os.path.join(base_dir, "..", "templates", template_name)
            fallback_path = os.path.normpath(fallback_path)  # normalize to eliminate .., etc.

            try:
                if os.path.exists(fallback_path):
                    with open(fallback_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    return Environment(autoescape=select_autoescape(['html', 'xml'])).from_string(content).render(**context)
            except Exception as fallback_error:
                logger.error(f"Failed to load template '{template_name}' from fallback path: {fallback_error}")

            logger.warning(f"Template '{template_name}' not found or failed to load; rendering inline. Error: {e}")
            return self._inline(context)

    def _inline(self, context: dict) -> str:
        # Build a simple readable HTML content using context data
        body = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f9f9f9;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    padding: 20px;
                    background: #fff;
                    border-radius: 5px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .logo {{
                    text-align: center;
                    margin-bottom: 20px;
                }}
                .otp {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #007BFF;
                }}
                .footer {{
                    margin-top: 20px;
                    font-size: 12px;
                    text-align: center;
                    color: #888;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">
                    <img src="{context.get('logo_url', '')}" height="60" alt="Organization Logo"/>
                </div>
                <h2>Hello {context.get("username", "User")},</h2>
                <p>Here is your verification code:</p>
                <p class="otp">{context.get("otp", "N/A")}</p>
                <p>If you didn't request this, please ignore the email.</p>
                <div class="footer">
                    Powered by your GI-KACE.
                </div>
            </div>
        </body>
        </html>
        """
        return body

# ---------- Core Email Service ----------
class EmailService:
    def __init__(
        self,
        tenant_id: str,
        db: Session,
        default_settings: TenantEmailSettings
    ):
        self.tenant_id = tenant_id
        self.db = db
        self.default = default_settings
        # Determine tenant settings, fallback to default
        tenant_cfg = self._load_tenant_settings()
        self.settings = tenant_cfg or self.default
        self.provider = self._init_provider(self.settings)
        # Look for tenant templates under templates/tenants/{tenant_id}/
        tenant_dir = os.path.join("templates", "tenants", tenant_id)
        self.renderer = TemplateRenderer(
            tenant_templates_dir=tenant_dir,
            global_templates_dir=self.settings.templates_dir
        )
        # self.renderer = TemplateRenderer(self.settings.templates_dir)

    def _load_tenant_settings(self) -> Optional[TenantEmailSettings]:
        if self.default.schema_based:
            # --- App 1: Schema-per-tenant ---
            # Read JSON from public.organization.settings column
            row = self.db.execute(
                text("SELECT settings FROM public.organization WHERE id = :id"),
                {"id": self.tenant_id}
            ).scalar_one_or_none()
            cfg_json = row
        else:
            # --- App 2: Shared public schema ---
            # Read JSON from system_settings table
            row = self.db.execute(
                text("SELECT setting_value FROM public.system_settings WHERE organization_id = :id AND setting_name = 'email'"),
                {"id": self.tenant_id}
            ).scalar_one_or_none()
            cfg_json = row
        if not cfg_json:
            return None
        return TenantEmailSettings.parse_obj(cfg_json)

    def _init_provider(self, cfg: TenantEmailSettings) -> EmailProvider:
        if cfg.provider == 'smtp':
            return SMTPProvider(cfg.host, cfg.port, cfg.username, cfg.password, cfg.use_tls)
        if cfg.provider == 'sendgrid':
            return SendGridProvider(cfg.api_key)
        raise ValueError(f"Unsupported email provider: {cfg.provider}")

    def test_connection(self) -> None:
        try:
            self.provider.test_connection()
        except Exception as e:
            raise ConnectionError(f"Email connection failed for tenant {self.tenant_id}: {e}")

    def send_email(
        self,
        to: List[str],
        subject: str,
        template_name: str,
        context: dict,
        attachments: List[str] = None
    ) -> None:
        # Validate connectivity
        self.test_connection()
        print("\n\n\n\nFrom: ", self.settings.default_from)
        # Build MIME message
        msg = MIMEMultipart()
        msg['From'] = self.settings.default_from
        msg['To'] = ','.join(to)
        msg['Subject'] = subject

        # Inject logo URL if available
        if self.settings.logo_path:
            context['logo_url'] = self.settings.logo_path

        body_html = self.renderer.render(template_name or "", context)
        # if not body_html:
        #     raise HTTPException(
        #         status_code=500,
        #         detail=f"Failed to render email template '{template_name}'."
        #     )
        msg.attach(MIMEText(body_html, 'html'))

        # Attach extra files
        for path in attachments or []:
            try:
                if not os.path.exists(path):
                    logger.error(f"Attachment not found: {path}")
                    continue
                filename = os.path.basename(path)
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)
            except Exception as e:
                logger.exception(f"Failed to attach file: {path}. Reason: {str(e)}")
            #     part = MIMEBase('application', 'octet-stream')
            #     with open(path, 'rb') as f:
            #         part.set_payload(f.read())
            #     encoders.encode_base64(part)
            #     # part.add_header('Content-Disposition', f'attachment; filename="{path.split('/')[-1]}"')
            #     filename = _p.basename(path)
            #     part.add_header(
            #         'Content-Disposition',
            #         f"attachment; filename=\"{filename}\""
            #     )
            #     msg.attach(part)
            # except Exception as e:
            #     logger.error(f"Failed to attach {path}: {e}")

        # Dispatch
        self.provider.send_message(msg)