# main.py (or wherever you create your FastAPI `app`)
import asyncio
from fastapi import FastAPI
from logging import getLogger

# Alembic programmatic API
from alembic import command
from alembic.config import Config

logger = getLogger(__name__)

# app = FastAPI(title="Staff Records API")


def run_migrations():
    """
    Programmatically run Alembic 'upgrade head' using alembic.ini
    """
    alembic_cfg = Config("alembic.ini")
    # If your DATABASE_URL is set via env var, Alembic will pick it up
    # from alembic.ini if you've used ${DATABASE_URL} there.
    logger.info("Starting database migrations...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations complete.")


# @app.on_event("startup")
# async def on_startup():
#     # Run migrations **once** before the app starts serving requests.
#     # We run it in a background thread via asyncio.to_thread() so that,
#     # if you ever adopt an async worker, you won’t block the event loop.
#     await asyncio.to_thread(run_migrations)

    # ... any other startup tasks ...


# Mount your routers here
# from app.api import departments, ...
# app.include_router(departments.router)

# If you want to expose a **secured** UI for migrations (not recommended unless you
# really need ad-hoc migration control), you could add an endpoint protected
# by your admin/OAuth2 scopes that calls `run_migrations()` on demand.
