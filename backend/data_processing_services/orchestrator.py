from celery import Celery
from context_extraction import extract_context
from classification import classify_mention
import os
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import re
from datetime import datetime
import math
import hashlib
import json
import redis
import sys
from pathlib import Path

load_dotenv()

# Конфигурация Celery
redis_url = os.getenv("REDIS_URL", "")
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

app = Celery(
    'data_processing',
    broker=broker_url,
    backend=result_backend,
)

app.config_from_object('celeryconfig')

# Настраиваем логирование
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def _safe_str(v) -> str:
    return "" if v is None else str(v)

def _quick_score(case_data: dict, query: str) -> float:
    """
    Быстрый скоринг без LLM: частота упоминаний + бонус за свежесть + бонус за явную роль из API.
    Нужен для top-N отбора, чтобы уложиться в SLA.
    """
    text = _safe_str(case_data.get("act_text", ""))
    api_context = _safe_str(case_data.get("context", ""))
    hay = f"{api_context}\n{text}"

    q = _safe_str(query).strip()
    if not q or not hay:
        mentions = 0
    else:
        try:
            mentions = len(re.findall(re.escape(q), hay, re.IGNORECASE))
        except re.error:
            mentions = hay.lower().count(q.lower())

    role = _safe_str(case_data.get("type_of_mention", "")).lower()
    role_bonus = 0.0
    if any(k in role for k in ("истец", "ответчик")):
        role_bonus = 0.35
    elif any(k in role for k in ("участник", "треть", "контрагент")):
        role_bonus = 0.2

    # Свежесть (если date в ISO/ YYYY-MM-DD)
    recency_bonus = 0.0
    date_str = _safe_str(case_data.get("date", ""))
    try:
        d = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else None
        if d:
            days = (datetime.now(d.tzinfo) - d).days if d.tzinfo else (datetime.now() - d).days
            # чем меньше дней, тем выше бонус (до ~0.25)
            recency_bonus = max(0.0, min(0.25, 0.25 * (1.0 - (days / 3650.0))))
    except Exception:
        recency_bonus = 0.0

    # Нормируем частоту: 1 упоминание ~0.15, 5+ ~0.6
    freq_score = min(mentions / 8.0, 1.0) * 0.6
    return min(1.0, freq_score + role_bonus + recency_bonus)

def _tokenize(text: str) -> list[str]:
    # простая токенизация для RU/EN + цифры (ИНН/ОГРН)
    return re.findall(r"[a-zа-яё0-9]+", (text or "").lower(), flags=re.IGNORECASE)

def _bm25_scores(docs: list[str], query: str, k1: float = 1.2, b: float = 0.75) -> list[float]:
    """
    Okapi BM25 для небольшого набора документов (кандидаты из API).
    Возвращает score на документ.
    """
    tokenized_docs = [_tokenize(d) for d in docs]
    N = len(tokenized_docs) or 1
    avgdl = (sum(len(d) for d in tokenized_docs) / N) if N else 0.0
    q_terms = _tokenize(query)
    if not q_terms:
        return [0.0 for _ in docs]

    # document frequency
    df = {}
    for d in tokenized_docs:
        seen = set(d)
        for t in seen:
            df[t] = df.get(t, 0) + 1

    # idf
    idf = {}
    for t in set(q_terms):
        n = df.get(t, 0)
        idf[t] = math.log(1.0 + (N - n + 0.5) / (n + 0.5))

    scores = []
    for d in tokenized_docs:
        dl = len(d) or 1
        tf = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1

        s = 0.0
        for t in q_terms:
            if t not in tf:
                continue
            f = tf[t]
            denom = f + k1 * (1.0 - b + b * (dl / (avgdl or 1.0)))
            s += idf.get(t, 0.0) * (f * (k1 + 1.0)) / (denom or 1.0)
        scores.append(s)
    return scores

def _minmax_norm(vals: list[float]) -> list[float]:
    if not vals:
        return []
    mn = min(vals)
    mx = max(vals)
    if mx - mn < 1e-9:
        return [0.0 for _ in vals]
    return [(v - mn) / (mx - mn) for v in vals]

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))

_EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
_EMBED_TTL = int(os.getenv("EMBEDDING_TTL_SECONDS", "604800"))  # 7 суток

# Импортируем apply_openai_proxy_env из backend/utils.py (без жёстких зависимостей на пакетную структуру)
_backend_path = str(Path(__file__).parent.parent)  # .../backend
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)
try:
    from utils import apply_openai_proxy_env  # type: ignore
except Exception:
    apply_openai_proxy_env = None  # type: ignore

def _redis_client():
    try:
        return redis.from_url(redis_url, decode_responses=False)
    except Exception:
        return None

def _embed_cache_key(text: str) -> str:
    h = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return f"embedding:{_EMBED_MODEL}:{h}"

from typing import Optional, List
from utils import get_openai_api_key, apply_openai_proxy_env

def _get_embedding(text: str) -> Optional[List[float]]:
    """
    Берём эмбеддинг из Redis кэша, иначе считаем через OpenAI embeddings API.
    Если ключа нет — возвращаем None (падаем на BM25-only).
    """
    api_key = get_openai_api_key()
    if not api_key:
        return None

    r = _redis_client()
    key = _embed_cache_key(text)
    if r:
        try:
            cached = r.get(key)
            if cached:
                obj = json.loads(cached.decode("utf-8"))
                if isinstance(obj, list):
                    return [float(x) for x in obj]
        except Exception:
            pass

    try:
        from openai import OpenAI
        apply_openai_proxy_env()
        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(model=_EMBED_MODEL, input=text)
        emb = resp.data[0].embedding
        if r:
            try:
                r.setex(key, _EMBED_TTL, json.dumps(emb).encode("utf-8"))
            except Exception:
                pass
        return emb
    except Exception:
        return None

@app.task
def process_case_data(case_data: dict, query: str):
    """
    Обработка данных одного дела
    """
    case_number = case_data.get("case_number", "")
    act_text = case_data.get("act_text", "")
    
    act_text_len = len(act_text) if act_text else 0
    logger.info(f"[PROCESS_CASE_DATA] Обработка дела {case_number}, query={query}")
    logger.info(f"[PROCESS_CASE_DATA] act_text присутствует: {bool(act_text)}, длина: {act_text_len} символов")
    if act_text:
        logger.info(f"[PROCESS_CASE_DATA] Первые 300 символов act_text: {act_text[:300]}")
        logger.info(f"[PROCESS_CASE_DATA] Последние 300 символов act_text: {act_text[-300:]}")
        if act_text_len < 100:
            logger.error(f"[PROCESS_CASE_DATA] КРИТИЧНО: act_text слишком короткий ({act_text_len} символов)! LLM не сможет обработать!")
    else:
        logger.error(f"[PROCESS_CASE_DATA] КРИТИЧНО: act_text ПУСТОЙ для дела {case_number}!")
    
    # ВАЖНО: не запускаем вложенные Celery group/.get() внутри Celery worker.
    # Это частая причина дедлоков и таймаутов.
    # Вместо этого выполняем агентов локально (параллельно в потоках, т.к. операции I/O-bound).
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_context = executor.submit(extract_context, case_number, act_text, query)
        f_classification = executor.submit(classify_mention, case_number, act_text, query)

        context_result = f_context.result() or {}
        classification_result = f_classification.result() or {}
        
        logger.info(f"[PROCESS_CASE_DATA] context_result: {context_result}")
        logger.info(f"[PROCESS_CASE_DATA] classification_result: {classification_result}")
    
    # Объединяем результаты
    # Собираем итоговую запись.
    # По ТЗ пользователю нужен контекст (фрагмент) + метаданные + ссылка, а не весь текст акта.
    processed_case = {**case_data}
    processed_case.pop("act_text", None)  # не тащим полный текст дальше (БД/кэш/экспорт)

    # Определяем финальный тип упоминания:
    # 1. Если есть классификация от LLM - используем её
    # 2. Если нет, но есть type_of_mention из API - переводим и используем
    # 3. Иначе - "упомянутое лицо" (по умолчанию)
    final_classification = classification_result.get("classification", "")
    api_type = case_data.get("type_of_mention", "")
    
    # Если LLM вернул "не найдено" или пусто, но есть тип из API - используем перевод
    if (not final_classification or final_classification == "не найдено") and api_type:
        # Переводим тип из API на русский
        type_translations = {
            "plaintiff": "истец",
            "creditor": "кредитор", 
            "defendant": "ответчик",
            "debtor": "должник",
            "thirdPerson": "третье лицо",
            "other": "иное лицо"
        }
        # Берем первый тип из списка (если несколько через запятую)
        api_type_clean = api_type.split(',')[0].strip()
        final_classification = type_translations.get(api_type_clean, "участник")
    
    # Если всё ещё нет классификации - используем "упомянутое лицо" по умолчанию
    if not final_classification or final_classification == "не найдено":
        final_classification = "упомянутое лицо"

    processed_case.update({
        "context": context_result.get("full_context") or context_result.get("context", ""),
        "mentions_count": context_result.get("mentions_count", processed_case.get("metadata", {}).get("mentions_count", 0)),
        "classification": final_classification,  # Используем финальную классификацию с учетом API и LLM
        "classification_confidence": classification_result.get("confidence", 0.0),
        # relevance_score теперь задаём гибридом BM25+embeddings на уровне батча (см. process_batch)
        "relevance_score": float(case_data.get("_hybrid_score", case_data.get("relevance_score", 0.0)) or 0.0),
        "extraction_confidence": context_result.get("confidence", 0.0),
        "type_of_mention": api_type,  # Сохраняем оригинальный тип из API для справки
    })
    
    return processed_case

@app.task
def process_batch(cases: list, query: str):
    """
    Параллельная обработка батча дел через Celery
    """
    # Top-N стратегия: быстрый скоринг для всех, LLM только для top-N.
    # Это снижает стоимость и резко улучшает время ответа (ТЗ: ≤ 15s).
    # Для демо/прод-сценария по умолчанию держим top-N небольшим:
    # иначе даже при 89 кейсах и медленном прокси обработка может занять 10+ минут,
    # и upstream (HTTP) будет казаться "вечным".
    top_n = int(os.getenv("LLM_TOP_N", "5"))
    top_n = max(0, min(top_n, len(cases)))

    # 1) BM25 по всем кандидатам (очень дёшево)
    doc_texts = []
    for c in cases:
        parts = [
            _safe_str(c.get("context", "")),
            _safe_str(c.get("court", "")),
            _safe_str(c.get("case_number", "")),
            _safe_str(c.get("act_type", "")),
            _safe_str(c.get("parties", "")),
            _safe_str(c.get("act_text", "")),
        ]
        doc_texts.append("\n".join([p for p in parts if p]))

    bm25_raw = _bm25_scores(doc_texts, query)
    bm25 = _minmax_norm(bm25_raw)

    # 2) Embeddings на top-M по BM25 (ограничиваем стоимость)
    # Эмбеддинги — дорого в холодном кэше. По умолчанию ограничиваем.
    top_m = int(os.getenv("EMBED_TOP_M", "40"))
    top_m = max(0, min(top_m, len(cases)))

    idx_sorted = sorted(range(len(cases)), key=lambda i: bm25[i], reverse=True)
    idx_top_m = idx_sorted[:top_m]

    query_emb = _get_embedding(query)
    emb_sim = [0.0 for _ in cases]
    if query_emb:
        for i in idx_top_m:
            e = _get_embedding(doc_texts[i])
            if e:
                # cosine в [-1..1], приводим к [0..1]
                emb_sim[i] = (_cosine(query_emb, e) + 1.0) / 2.0

    # 3) Комбинация (веса можно тюнить)
    w_bm25 = float(os.getenv("WEIGHT_BM25", "0.55"))
    w_emb = float(os.getenv("WEIGHT_EMB", "0.45"))
    base = []
    for i in range(len(cases)):
        # лёгкие эвристики как tie-breaker
        heur = _quick_score(cases[i], query) * 0.15
        score = (bm25[i] * w_bm25) + (emb_sim[i] * w_emb) + heur
        score = max(0.0, min(1.0, score))
        cases[i]["_hybrid_score"] = score
        base.append(score)

    # Выбираем top-N для LLM по гибридному score
    idx_sorted2 = sorted(range(len(cases)), key=lambda i: base[i], reverse=True)
    idx_top_n = set(idx_sorted2[:top_n])
    top_cases = [cases[i] for i in idx_sorted2[:top_n]]
    tail_cases = [cases[i] for i in idx_sorted2[top_n:]]

    results = []

    # LLM-обработка для top-N
    # ВАЖНО: если обрабатывать top-N последовательно, общая задержка становится N * (latency LLM),
    # что легко превращается в 10-15 минут при прокси/ретраях.
    # Поэтому делаем параллельную обработку по кейсам (I/O-bound) через пул потоков.
    # Дефолт для демо: 8 параллельных кейсов (можно переопределить env LLM_MAX_WORKERS)
    llm_workers = int(os.getenv("LLM_MAX_WORKERS", "8"))
    llm_workers = max(1, min(llm_workers, max(1, len(top_cases))))
    if top_cases:
        with ThreadPoolExecutor(max_workers=llm_workers) as executor:
            futures = [executor.submit(process_case_data, case, query) for case in top_cases]
            for f in futures:
                try:
                    results.append(f.result())
                except Exception:
                    # fallback: если один кейс упал, всё равно продолжаем
                    results.append(process_case_data({}, query))

    # Остальные — без LLM: используем то, что уже пришло от API + быстрый score
    for case in tail_cases:
        processed_case = {**case}
        processed_case.pop("act_text", None)
        processed_case.update({
            "context": processed_case.get("context", ""),
            "mentions_count": processed_case.get("metadata", {}).get("mentions_count", 0),
            "classification": processed_case.get("type_of_mention", "") or "упоминание",
            "classification_confidence": 0.0,
            "relevance_score": float(case.get("_hybrid_score", 0.0) or 0.0),
            "extraction_confidence": 0.0,
        })
        results.append(processed_case)

    return results


if __name__ == "__main__":
    app.start()
