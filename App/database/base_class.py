from uuid import UUID as UUID_V
import inflect
import typing as t
from sqlalchemy.ext.declarative import declared_attr, as_declarative, declarative_base
from sqlalchemy import Column, String,  DateTime
import datetime
from sqlalchemy.dialects.postgresql import UUID
from typing import Any
import uuid
from functools import reduce


class_registry: t.Dict = {}


def change_case(str):
    return reduce(lambda x, y: x + ('_' if y.isupper() else '') + y, str).lower()


@as_declarative(class_registry=class_registry)
class Base:
    id: Any
    __name__: str
    
    
    # Generate __tablename__ automatically
    @declared_attr
    def __tablename__(cls) -> str:
        camel_check = change_case(cls.__name__)
        p = inflect.engine()
        return p.plural(camel_check.lower())
    





@as_declarative(class_registry=class_registry)
class APIBase():

    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True,index=True, nullable=False, default=uuid.uuid4)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime,  onupdate=datetime.datetime.utcnow)

