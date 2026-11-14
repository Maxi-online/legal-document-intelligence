from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Case(Base):
    'Case model in database'
    __tablename__ = "cases"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, index=True)
    case_number = Column(String, index=True)
    court = Column(String)
    date = Column(DateTime)
    act_url = Column(String)
    parties = Column(Text)
    act_text = Column(Text)
    act_type = Column(String)
    context = Column(Text)
    type_of_mention = Column(String, index=True)  # Type of reference from API Casebook
    classification = Column(String, index=True)  # Classification from GPT (claimer/defendant, etc.)
    relevance_score = Column(Float, index=True)
    extraction_confidence = Column(Float)
    case_metadata = Column(JSON)  # Renamed metadata because metadata is reserved in SQLAlchemy
    created_at = Column(DateTime, default=datetime.now)
