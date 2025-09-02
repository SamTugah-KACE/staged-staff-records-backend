# src/services/data_input_handlers.py
from typing import Callable, Dict
from sqlalchemy.orm import Session
from Models.models import EmployeeDataInput
import pkgutil, importlib, logging


Handler = Callable[[Session, EmployeeDataInput], None]
_registry: Dict[str, Handler] = {}

logger = logging.getLogger(__name__)

def register_handler(data_type: str):
    def decorator(fn: Handler):
        _registry[data_type] = fn
        return fn
    return decorator

# def get_handler(data_type: str) -> Handler:
#     if data_type not in _registry:
#         raise ValueError(f"No handler registered for data_type={data_type}")
#     return _registry[data_type]

def get_handler(data_type: str) -> Handler:
    try:
        return _registry[data_type]
    except KeyError:
        logger.error("No handler registered for data_type=%s", data_type)
        raise ValueError(f"No handler registered for data_type={data_type}")


def autodiscover_handlers():
    """
    Auto-import all modules under src/services/handlers
    so that @register_handler decorators are executed.
    """
    package = 'Service.handlers'
    package_path = importlib.import_module(package).__path__
    for _, name, _ in pkgutil.iter_modules(package_path):
        importlib.import_module(f"{package}.{name}")