from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Table, create_engine
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
# from sqlalchemy.exc import SQLAlchemyError
from database.db_session import BaseModel
# from Models.models import DataBank
# import logging


# Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


class Role(BaseModel):
    __tablename__ = "roles"

    name = Column(String, nullable=False)
    permissions = Column(JSONB, nullable=True)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    organization = relationship("Organization", back_populates="roles")
    users = relationship(
        "User",
        back_populates="role",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )






# def create_default_roles(db: Session):
#     """
#     Efficiently seeds default roles into the databank table.
#     Ensures atomicity, handles duplicates, and appends new roles to the existing structure.
#     """
#     roles = [
#         {"name": "Admin", "permissions": {"admin": True}},
#         {"name": "User", "permissions": {"admin": False}},
#     ]

#     try:
#         with db.begin():  # Begin a transaction
#             # Fetch or create the databank entry for roles
#             databank_entry = db.query(DataBank).filter(DataBank.data_name == "roles").first()

#             if not databank_entry:
#                 # If no existing entry, create a new one
#                 databank_entry = DataBank(data_name="roles", data=roles)
#                 db.add(databank_entry)
#             else:
#                 # Check for duplicates and append new roles
#                 existing_roles = databank_entry.data
#                 new_roles = [
#                     role for role in roles
#                     if not any(existing_role["name"] == role["name"] for existing_role in existing_roles)
#                 ]
#                 if new_roles:
#                     databank_entry.data.extend(new_roles)  # Append only unique roles

#             # Commit changes
#             db.commit()
#             logger.info("Default roles seeded successfully.")

#     except SQLAlchemyError as e:
#         db.rollback()
#         logger.error(f"An error occurred while seeding default roles: {str(e)}")
#         raise RuntimeError("Failed to seed default roles. Please check the logs.") from e
