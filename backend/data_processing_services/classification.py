from celery import Celery
from openai import AsyncOpenAI
import json
import sys
import logging
from pathlib import Path

# Добавляем путь к backend для импорта utils
backend_path = str(Path(__file__).parent.parent.parent)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
from utils import get_openai_api_key
from utils import apply_openai_proxy_env

app = Celery('classification')
app.config_from_object('celeryconfig')

# Настраиваем логирование для Celery - используем root logger, который Celery уже настроил
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

_client = None

def _get_client():
    global _client
    if _client is None:
        apply_openai_proxy_env()
        _client = AsyncOpenAI(api_key=get_openai_api_key())
    return _client

@app.task
def classify_mention(case_number: str, act_text: str, query: str) -> dict:
    """
    Классификация роли упомянутого лица в деле
    
    Args:
        case_number: Номер дела
        act_text: Текст судебного акта
        query: Поисковый запрос (ФИО/ИНН/наименование)
    
    Returns:
        Словарь с классификацией роли
    """
    try:
        system_prompt = """Ты - эксперт по классификации участников судебных процессов. Твоя задача - точно определять роли лиц в судебных делах.

Определи тип упоминания указанного лица/организации в судебном деле. Возможные типы согласно ТЗ:
- "участник" - лицо является стороной дела (истец, ответчик, третье лицо, кредитор, должник)
- "упомянутое лицо" - лицо упоминается в тексте акта, но не является участником дела
- "контрагент" - лицо является стороной договора или сделки, упомянутой в деле
- "аффилированное лицо" - лицо связано с участником дела (учредитель, руководитель, связанная компания)

Правила классификации:
1. Если лицо является участником дела (сторона, третье лицо) - верни "участник"
2. Если лицо упоминается в тексте, но НЕ является участником - верни "упомянутое лицо"
3. Если лицо упоминается как сторона договора/сделки - верни "контрагент"
4. Если лицо связано с участником (учредитель, руководитель и т.д.) - верни "аффилированное лицо"

ВАЖНО: Ты должен вернуть результат в формате JSON объекта. Структура JSON:
{
    "classification": "название_типа",
    "confidence": число_от_0_до_1,
    "reasoning": "краткое обоснование классификации"
}

Если упоминание не найдено в тексте, верни:
{
    "classification": "не найдено",
    "confidence": 0.0,
    "reasoning": "Упоминание не обнаружено в тексте"
}"""

        user_prompt = f"""Текст судебного акта:
{act_text}

Классифицируй роль: {query}"""

        import asyncio
        
        async def get_response():
            logger.info(f"[CLASSIFICATION] Запрос к OpenAI для дела {case_number}, query={query}")
            logger.info(f"[CLASSIFICATION] Длина act_text: {len(act_text) if act_text else 0}")
            if act_text:
                logger.info(f"[CLASSIFICATION] Первые 500 символов act_text: {act_text[:500]}")
            else:
                logger.warning(f"[CLASSIFICATION] act_text ПУСТОЙ для дела {case_number}!")
            
            response = await _get_client().chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            response_text = response.choices[0].message.content
            logger.info(f"[CLASSIFICATION] Ответ от OpenAI (первые 500 символов): {response_text[:500] if response_text else 'EMPTY'}")
            return response_text
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        response_text = loop.run_until_complete(get_response())
        
        if not response_text:
            return {
                "classification": "не определено",
                "confidence": 0.0,
                "reasoning": "Пустой ответ от LLM"
            }
        
        # GPT-5 с response_format={"type": "json_object"} возвращает чистый JSON
        # Но на всякий случай очищаем от возможных markdown блоков
        cleaned_text = response_text.strip()
        
        # Убираем markdown code blocks если есть (на случай если модель все же вернула)
        if "```" in cleaned_text:
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned_text, re.DOTALL)
            if json_match:
                cleaned_text = json_match.group(1)
            else:
                parts = cleaned_text.split("```")
                if len(parts) >= 3:
                    cleaned_text = parts[1].strip()
                    if cleaned_text.startswith("json"):
                        cleaned_text = cleaned_text[4:].strip()
        
        # Пытаемся найти JSON объект в тексте (на случай если есть лишний текст)
        json_start = cleaned_text.find("{")
        json_end = cleaned_text.rfind("}")
        if json_start != -1 and json_end != -1 and json_end > json_start:
            cleaned_text = cleaned_text[json_start:json_end+1]
        
        try:
            result = json.loads(cleaned_text)
            logger.info(f"[CLASSIFICATION] Успешно распарсен JSON для дела {case_number}: {result}")
            
            # Проверяем, что классификация валидна
            classification = result.get("classification", "")
            if not classification or classification == "не найдено":
                # Проверяем, действительно ли query есть в тексте
                if query.lower() in act_text.lower() if act_text else False:
                    # Query есть в тексте, но LLM не нашел - используем fallback
                    logger.warning(f"[CLASSIFICATION] LLM не нашел классификацию для дела {case_number}, но query есть в тексте. Используем fallback.")
                    result["classification"] = "упомянутое лицо"
                    result["confidence"] = 0.5
                    result["reasoning"] = "Упоминание найдено в тексте, но LLM не определил роль"
            
            return result
        except json.JSONDecodeError as e:
            # Пытаемся извлечь классификацию из текста согласно ТЗ
            response_lower = response_text.lower() if response_text else ""
            classification = "упомянутое лицо"  # По умолчанию, если не участник
            
            # Проверяем по приоритету согласно ТЗ
            if any(word in response_lower for word in ["участник", "сторона", "истец", "ответчик", "третье лицо", "кредитор", "должник"]):
                classification = "участник"
            elif "контрагент" in response_lower or "договор" in response_lower or "сделка" in response_lower:
                classification = "контрагент"
            elif any(word in response_lower for word in ["аффилирован", "учредитель", "руководитель", "связан"]):
                classification = "аффилированное лицо"
            elif "упомянут" in response_lower or "упоминается" in response_lower:
                classification = "упомянутое лицо"
            
            return {
                "classification": classification,
                "confidence": 0.6,
                "reasoning": response_text[:200] if response_text else "Классификация выполнена"
            }
            
    except Exception as e:
        logger.error(f"[CLASSIFICATION] Ошибка для дела {case_number}: {e}", exc_info=True)
        return {
            "classification": "не определено",
            "confidence": 0.0,
            "reasoning": f"Ошибка при классификации: {str(e)}"
        }
