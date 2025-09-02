# ---------- DEFAULT EMAIL SETTINGS VIA APPLICATION CONFIG ----------
# For App2 (Shared Schema), use BaseConfig
from Schemas.schemas import TenantEmailSettings
from Utils.config import config as base_config  # config.py in App2
app2_cfg = base_config
DEFAULT_EMAIL_SETTINGS = TenantEmailSettings(
    provider=app2_cfg.PROVIDER if app2_cfg.USE_CREDENTIALS else 'smtp',
    host=app2_cfg.MAIL_SERVER,
    port=app2_cfg.MAIL_PORT,
    username=app2_cfg.MAIL_USERNAME,
    password=app2_cfg.MAIL_PASSWORD,
    use_tls=app2_cfg.MAIL_STARTTLS,
    default_from=app2_cfg.MAIL_FROM,
    templates_dir=app2_cfg.EMAIL_TEMPLATES_DIR if hasattr(app2_cfg, 'EMAIL_TEMPLATES_DIR') else 'templates/emails',
    logo_path=None,
    api_key=None,
    schema_based=False
)