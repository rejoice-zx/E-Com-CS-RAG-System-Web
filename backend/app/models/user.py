"""User Model"""
from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base
from app.utils.time import utcnow, UTCDateTime


class User(Base):
    """User database model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(20), default="cs")  # admin, cs, or customer
    display_name = Column(String(100))
    email = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(UTCDateTime, default=utcnow)
    last_login = Column(UTCDateTime)
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
