# Models/daily_check_log.py
from sqlalchemy import Column, Integer, Date, UniqueConstraint
from database.db_session import BaseModel

class DailyCheckLog(BaseModel):
    __tablename__ = "daily_check_log"
    
    # id = Column(Integer, primary_key=True, autoincrement=True)
    check_date = Column(Date, nullable=False, unique=True)
    
    __table_args__ = (
        UniqueConstraint("check_date", name="uq_daily_check_date"),
    )
