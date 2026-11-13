from celery import Celery
from openai import AsyncOpenAI
import json
import re
import sys
from pathlib import Path

# Добавляем путь к backend для импорта utils
backend_path = str(Path(__file__).parent.parent.parent)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
from utils import get_openai_api_key
from utils import apply_openai_proxy_env

app = Celery('ranking')
app.config_from_object('celeryconfig')

_client = None

def _get_client():
    global _client
    if _client is None:
        apply_openai_proxy_env()
        _client = AsyncOpenAI(api_key=get_openai_api_key())
    return _client

@app.task
def rank_relevance(case_number: str, act_text: str, query: str) -> dict:
    """
    Ранжирование релевантности упоминания
    
    Args:
        case_number: Номер дела
        act_text: Текст судебного акта
        query: Поисковый запрос (ФИО/ИНН/наименование)
    
    Returns:
        Словарь с оценкой релевантности
    """
    try:
        # Подсчитываем частоту упоминаний
        mentions_count = len(re.findall(re.escape(query), act_text, re.IGNORECASE))
        
        prompt = f"""Оцени релевантность упоминания "{query}" в следующем судебном акте.

Текст судебного акта:
{act_text}

Количество упоминаний "{query}": {mentions_count}

Оцени релевантность по следующим критериям:
1. Частота упоминаний (больше упоминаний = выше релевантность)
2. Важность роли в деле (истец/ответчик важнее свидетеля)
3. Ключевые моменты упоминания (участие в решениях, наличие обязательств и т.д.)
4. Актуальность упоминания для поискового запроса

Верни результат в формате JSON:
{{
    "relevance_score": число_от_0_до_1,
    "factors": {{
        "mention_frequency": число,
        "role_importance": число_от_0_до_1,
        "context_importance": число_от_0_до_1,
        "overall_relevance": число_от_0_до_1
    }},
    "explanation": "краткое объяснение оценки"
}}

Если "{query}" не найден в тексте, верни:
{{
    "relevance_score": 0.0,
    "factors": {{
        "mention_frequency": 0,
        "role_importance": 0.0,
        "context_importance": 0.0,
        "overall_relevance": 0.0
    }},
    "explanation": "Упоминание не найдено"
}}
"""

        import asyncio
        
        async def get_response():
            response = await _get_client().chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": "Ты - эксперт по оценке релевантности документов. Твоя задача - точно оценивать важность упоминаний в судебных актах."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        response_text = loop.run_until_complete(get_response())
        
        try:
            result = json.loads(response_text)
            return result
        except json.JSONDecodeError:
            # Вычисляем базовую оценку на основе частоты упоминаний
            base_score = min(mentions_count / 10, 1.0) if mentions_count > 0 else 0.0
            
            return {
                "relevance_score": base_score,
                "factors": {
                    "mention_frequency": mentions_count,
                    "role_importance": 0.5,
                    "context_importance": 0.5,
                    "overall_relevance": base_score
                },
                "explanation": f"Оценка основана на частоте упоминаний: {mentions_count}"
            }
            
    except Exception as e:
        print(f"Error in ranking: {e}")
        # Базовая оценка на основе частоты упоминаний
        mentions_count = len(re.findall(re.escape(query), act_text, re.IGNORECASE)) if act_text else 0
        base_score = min(mentions_count / 10, 1.0) if mentions_count > 0 else 0.0
        
        return {
            "relevance_score": base_score,
            "factors": {
                "mention_frequency": mentions_count,
                "role_importance": 0.5,
                "context_importance": 0.5,
                "overall_relevance": base_score
            },
            "explanation": f"Ошибка при ранжировании: {str(e)}"
        }
