"""Knowledge Item Model"""
from sqlalchemy import Column, String, Text, Float, JSON
from app.database import Base
from app.utils.time import utcnow, UTCDateTime


class KnowledgeItem(Base):
    """Knowledge item database model"""
    __tablename__ = "knowledge_items"
    
    id = Column(String(50), primary_key=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    keywords = Column(JSON, default=list)
    category = Column(String(50), default="通用", index=True)
    score = Column(Float, default=1.0)
    created_at = Column(UTCDateTime, default=utcnow)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)
    
    def __repr__(self):
        return f"<KnowledgeItem(id='{self.id}', category='{self.category}')>"
