from .config import get_config
from fastapi import Depends
from Service.sms_service import (
    ArkeselSMSService, BaseSMSService
)



def get_sms_service(
    config = Depends(get_config),
) -> BaseSMSService:
    return ArkeselSMSService(
        api_key   = config.ARKESEL_API_KEY,
        sender_id = config.ARKESEL_SENDER_ID,
        use_case  = config.ARKESEL_USE_CASE,  #getattr(config, "ARKESEL_USE_CASE", None),
        timeout   = config.ARKESEL_TIMEOUT,
    )
