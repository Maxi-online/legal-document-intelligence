from pydantic import BaseModel
from typing import List, Optional, Dict

class CaseData(BaseModel):
    """Модель данных о деле из Casebook API"""
    case_number: str
    court: str
    date: str
    act_url: str
    parties: List[str]
    act_text: str
    act_type: str
    context: Optional[str] = None
    type_of_mention: Optional[str] = None
    metadata: Dict

class CasebookResponse(BaseModel):
    """Модель ответа от Casebook API"""
    items: List[CaseData]
    total: int
    limit: int
    offset: int
