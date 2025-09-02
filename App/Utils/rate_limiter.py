from datetime import datetime
import json
import os
import time
from collections import defaultdict
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from Models.models import User

class RateLimiter:
    """
    Multi-Tenant Rate Limiter for Login Attempts.
    
    Limits login attempts per user **within the same organization** over a given time window.
    """

    def __init__(self, max_attempts: int = 3, period: int = 60):
        """
        :param max_attempts: Maximum number of failed attempts allowed per user
        :param period: Time window in seconds before login attempts reset
        """
        self.max_attempts = max_attempts
        self.period = period
        self.failed_attempts = defaultdict(list)  # { org_id: { user_id: [timestamps] } }
    
    def _get_log_file(self, organization_id: str) -> str:
        """Returns the path for today's log file for the given organization."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_dir = f"./logs/{organization_id}"  # Log directory per organization
        os.makedirs(log_dir, exist_ok=True)  # Ensure directory exists
        return os.path.join(log_dir, f"{today}_failed_logins.log")

    def log_failed_attempt(self, user: User, request):
        """Logs the failed login attempt details into the organization's daily log file."""
        org_id = str(user.organization_id)
        log_file = self._get_log_file(org_id)

        device_info = request.headers.get("User-Agent", "Unknown Device")
        ip_address = request.client.host

        # Read existing logs if file exists
        attempts = {}
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                attempts = json.load(f)

        username = user.username
        if username in attempts:
            attempts[username]["attempts"] += 1
        else:
            attempts[username] = {
                "account_info": username,
                "device_info": device_info,
                "ip_address": ip_address,
                "attempts": 1
            }

        # Save updated log
        with open(log_file, "w") as f:
            json.dump(attempts, f, indent=4)



    def is_allowed(self, db: Session, user: User) -> bool:
        """
        Checks if the user can attempt login within their organization.
        """
        now = time.time()
        org_id = str(user.organization_id)  # Convert UUID to string for dict key
        user_id = str(user.id)

        # Initialize org in dict if not exists
        if org_id not in self.failed_attempts:
            self.failed_attempts[org_id] = defaultdict(list)

        # Remove expired attempts (older than `period` seconds)
        self.failed_attempts[org_id][user_id] = [
            timestamp for timestamp in self.failed_attempts[org_id][user_id] if now - timestamp < self.period
        ]

        # If the user has exceeded allowed attempts, block login
        if len(self.failed_attempts[org_id][user_id]) >= self.max_attempts:
            # Optionally, lock the user account
            user.is_active = False
            db.commit()

            raise HTTPException(status_code=429, detail="Too many failed login attempts. Account temporarily locked.")

        # Log the new failed attempt
        self.failed_attempts[org_id][user_id].append(now)
        return True

    def check_rate_limit(self, db: Session, user: User, request: Request):
        """
        Enforces the rate limit before allowing login attempts.
        """
        if not self.is_allowed(db, user):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Too many failed login attempts."
            )

    def reset_attempts(self, user: User):
        """
        Resets login attempts after a successful login.
        """
        org_id = str(user.organization_id)
        user_id = str(user.id)

        if org_id in self.failed_attempts and user_id in self.failed_attempts[org_id]:
            self.failed_attempts[org_id][user_id] = []
