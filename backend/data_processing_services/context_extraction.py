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

app = Celery('context_extraction')
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
def extract_context(case_number: str, act_text: str, query: str) -> dict:
    """
    Извлечение контекста упоминания из текста судебного акта
    
    Args:
        case_number: Номер дела
        act_text: Текст судебного акта
        query: Поисковый запрос (ФИО/ИНН/наименование)
    
    Returns:
        Словарь с контекстом упоминания и уверенностью
    """
    try:
        system_prompt = """Ты - эксперт по анализу юридических документов. Твоя задача - точно извлекать контекст упоминаний из судебных актов.

Инструкции:
1. Найди все упоминания указанного лица/организации в тексте судебного акта
2. Извлеки контекст каждого упоминания (окружающие предложения до и после)
3. Определи, в каком контексте упоминается лицо (например, как сторона дела, свидетелем, третьим лицом и т.д.)
4. Укажи ключевую информацию о роли и участии в деле
5. Подсчитай количество упоминаний

ВАЖНО: Ты должен вернуть результат в формате JSON объекта. Структура JSON:
{
    "context": "краткое описание контекста упоминания",
    "full_context": "полный контекст с окружающими предложениями",
    "mentions_count": число,
    "confidence": число_от_0_до_1
}

Если упоминание не найдено в тексте, верни:
{
    "context": "Упоминание не найдено",
    "full_context": "",
    "mentions_count": 0,
    "confidence": 0.0
}"""

        user_prompt = f"""Текст судебного акта:
{act_text}

Извлеки контекст упоминания: {query}"""

        import asyncio
        
        async def get_response():
            logger.info(f"[CONTEXT_EXTRACTION] Запрос к OpenAI для дела {case_number}, query={query}")
            logger.info(f"[CONTEXT_EXTRACTION] Длина act_text: {len(act_text) if act_text else 0}")
            if act_text:
                logger.info(f"[CONTEXT_EXTRACTION] Первые 500 символов act_text: {act_text[:500]}")
            else:
                logger.warning(f"[CONTEXT_EXTRACTION] act_text ПУСТОЙ для дела {case_number}!")
            
            response = await _get_client().chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            response_text = response.choices[0].message.content
            logger.info(f"[CONTEXT_EXTRACTION] Ответ от OpenAI (первые 500 символов): {response_text[:500] if response_text else 'EMPTY'}")
            return response_text
        
        # Для синхронного Celery используем run_async
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        response_text = loop.run_until_complete(get_response())
        
        if not response_text:
            return {
                "context": "",
                "full_context": "",
                "mentions_count": 0,
                "confidence": 0.0
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
        
        # Парсим JSON ответ
        try:
            result = json.loads(cleaned_text)
            
            # Проверяем, что контекст не содержит промпт или инструкции
            context = result.get("context", "") or result.get("full_context", "")
            if context and ("Задача:" in context or "Найди все упоминания" in context or "Извлеки контекст" in context or "Проанализируй следующий" in context or "Текст судебного акта:" in context):
                # Это промпт, а не контекст - очищаем
                result["context"] = ""
                result["full_context"] = ""
                result["mentions_count"] = 0
                result["confidence"] = 0.0
            
            logger.info(f"[CONTEXT_EXTRACTION] Успешно распарсен JSON для дела {case_number}: {result}")
            return result
        except json.JSONDecodeError as e:
            # Если не удалось распарсить JSON, пытаемся извлечь данные из текста напрямую
            logger.error(f"[CONTEXT_EXTRACTION] JSON decode error для дела {case_number}: {e}")
            logger.error(f"[CONTEXT_EXTRACTION] Response text: {response_text[:500]}")
            
            # Пытаемся найти упоминания в тексте напрямую
            import re
            query_escaped = re.escape(query)
            mentions = len(re.findall(query_escaped, act_text, re.IGNORECASE)) if act_text else 0
            
            if mentions > 0:
                # Находим первое упоминание и извлекаем контекст
                match = re.search(query_escaped, act_text, re.IGNORECASE)
                if match:
                    start = max(0, match.start() - 200)
                    end = min(len(act_text), match.end() + 200)
                    extracted_context = act_text[start:end].strip()
                    return {
                        "context": extracted_context,
                        "full_context": extracted_context,
                        "mentions_count": mentions,
                        "confidence": 0.7
                    }
            
            return {
                "context": "",
                "full_context": "",
                "mentions_count": 0,
                "confidence": 0.0
            }
            
    except Exception as e:
        logger.error(f"[CONTEXT_EXTRACTION] Ошибка для дела {case_number}: {e}", exc_info=True)
        return {
            "context": f"Ошибка при извлечении контекста: {str(e)}",
            "full_context": "",
            "mentions_count": 0,
            "confidence": 0.0
        }
