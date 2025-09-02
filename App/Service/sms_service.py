import logging, requests
from fastapi import HTTPException
from typing import List, Dict, Optional
from jinja2 import Template

logger = logging.getLogger(__name__)

# class BaseSMSService:
#     def send(self, phone: str, template_name: str, ctx: Dict) -> Dict:
#         raise NotImplementedError
#     def send_bulk(self, phones: List[str], template: str, ctxs: List[Dict]=None) -> List[Dict]:
#         raise NotImplementedError

# class ArkeselSMSService(BaseSMSService):
#     TEMPLATE_MAP = {
#         "org_signup": "Hello {{ first_name }}! Congratulations on signing up {{ org_name }} on our platform.",
#         "employee_created": "Hi {{ first_name }}, your account at {{ org_name }} is ready. Login at {{ signin_url }}."
#     }

#     def __init__(self, api_key, sender_id, use_case=None, timeout=15.0):
#         self.base_url = "https://sms.arkesel.com/sms/api"
#         self.api_key, self.sender_id = api_key, sender_id
#         self.use_case, self.timeout = use_case, timeout

#     def _render(self, name, ctx):
#         tpl = self.TEMPLATE_MAP.get(name)
#         if not tpl:
#             raise ValueError(f"Unknown template {name}")
#         return Template(tpl).render(**ctx)

#     def send(self, phone, template_name, ctx):
#         msg = self._render(template_name, ctx)
#         params = {
#             "action":  "send-sms",
#             "api_key": self.api_key,
#             "from":    self.sender_id,
#             "to":      phone,
#             "sms":     msg,
#         }
#         if self.use_case:
#             params["use_case"] = self.use_case
#         try:
#             r = requests.get(self.base_url, params=params, timeout=self.timeout)
#             r.raise_for_status()
#             return r.json()
#         except requests.RequestException as e:
#             logger.error(f"SMS error → {e}")
#             raise HTTPException(502, "SMS service unavailable")

#     def send_bulk(self, phones, template_name, ctxs=None):
#         results = []
#         if ctxs is None:
#             ctxs = [{}]*len(phones)
#         for p, c in zip(phones, ctxs):
#             results.append(self.send(p, template_name, c))
#         return results

class BaseSMSService:
    def send(self, phone: str, template_name: str, ctx: Dict,
             sender_id: Optional[str] = None, use_case: Optional[str] = None) -> Dict:
        raise NotImplementedError

    def send_bulk(self, phones: List[str], template_name: str, ctxs: List[Dict]=None,
                  sender_id: Optional[str] = None, use_case: Optional[str] = None) -> List[Dict]:
        raise NotImplementedError

class ArkeselSMSService(BaseSMSService):
    # Default templates – you can override or extend at runtime
    TEMPLATE_MAP = {
        "org_signup": "Hello {{ first_name }}! Congratulations on signing up {{ org_name }} on our platform.",
        "employee_created": "Hi {{ first_name }}, your account at {{ org_name }} is ready. Check your email at {{ email }} for your login credentials.",
        "user_account_updated": "Hi {{ first_name }}, your account at {{ org_name }} has been updated.\n\nPlease notify your system administrator, if you did not initiate such operation."
    }

    def __init__(self, api_key: str, sender_id: str,
                 use_case: str = None, timeout: float = 15.0):
        self.base_url   = "https://sms.arkesel.com/sms/api"
        self.api_key    = api_key
        self.default_sender = sender_id
        self.default_use_case = use_case
        self.timeout    = timeout

    def _render(self, template_name: str, ctx: Dict) -> str:
        tpl_str = self.TEMPLATE_MAP.get(template_name)
        if not tpl_str:
            raise ValueError(f"Unknown SMS template '{template_name}'")
        return Template(tpl_str).render(**ctx)

    def send(self, phone: str, template_name: str, ctx: Dict,
             sender_id: str = None, use_case: str = None) -> Dict:
        message = self._render(template_name, ctx)
        params = {
            "action":  "send-sms",
            "api_key": self.api_key,
            "from":    sender_id or self.default_sender,
            "to":      phone,
            "sms":     message,
        }
        uc = use_case or self.default_use_case
        if uc:
            params["use_case"] = uc
        try:
            r = requests.get(self.base_url, params=params, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.error(f"SMS error to {phone}: {e}")
            raise HTTPException(502, "SMS service unavailable")

    def send_bulk(self, phones: List[str], template_name: str, ctxs: List[Dict]=None,
                  sender_id: str = None, use_case: str = None) -> List[Dict]:
        ctxs = ctxs or [{}]*len(phones)
        results = []
        for p, c in zip(phones, ctxs):
            results.append(self.send(p, template_name, c, sender_id, use_case))
        return results
