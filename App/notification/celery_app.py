# celery_app.py

import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

# Securely load Redis URL (include password if set) from environment
broker_url = os.getenv("REDIS_URL", "redis://:yourpassword@localhost:6379/0")
result_backend = os.getenv("REDIS_URL", "redis://:yourpassword@localhost:6379/0")

celery_app = Celery("worker", broker=broker_url, backend=result_backend)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,           # Good for tasks that are long-running
    task_acks_late=True,                    # Ensure tasks are acknowledged after completion
    task_reject_on_worker_lost=True,        # In case of worker crash, task will be redelivered
    # Optionally add rate limits for specific tasks:
    task_annotations={
        'Utils.daily_checks.daily_checks': {'rate_limit': '1/m'},
    },
)

if __name__ == "__main__":
    celery_app.start()
