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

# Celery configuration
redis_url = os.getenv("REDIS_URL", "")
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

app = Celery(
    'data_processing',
    broker=broker_url,
    backend=result_backend,
)

app.config_from_object('celeryconfig')

# Adjusting Login
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
    Rapid Sorting Without LLM: Frequency of Reference + Bonus for Freshness + Bonus of API Explicit Role.
    Need top-N to fit into the SLA.
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
    elif any(k in role for k in ("участник", 'one third', "контрагент")):
        role_bonus = 0.2

    # Fresh (if data in ISO/YYYY-MM-DD)
    recency_bonus = 0.0
    date_str = _safe_str(case_data.get("date", ""))
    try:
        d = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else None
        if d:
            days = (datetime.now(d.tzinfo) - d).days if d.tzinfo else (datetime.now() - d).days
            # The shorter the days, the higher the bonus (to ~0.25)
            recency_bonus = max(0.0, min(0.25, 0.25 * (1.0 - (days / 3650.0))))
    except Exception:
        recency_bonus = 0.0

    # Normalized frequency: 1 reference ~0.15, 5+ ~0.6
    freq_score = min(mentions / 8.0, 1.0) * 0.6
    return min(1.0, freq_score + role_bonus + recency_bonus)

def _tokenize(text: str) -> list[str]:
    # simple currenting for RU/EN + digits (INN/DWP)
    return re.findall(r"[a-zа-яё0-9]+", (text or "").lower(), flags=re.IGNORECASE)

def _bm25_scores(docs: list[str], query: str, k1: float = 1.2, b: float = 0.75) -> list[float]:
    """
    Okapi BM25 for a small set of documents (API candidates)).
    Returns score to document.
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
_EMBED_TTL = int(os.getenv("EMBEDDING_TTL_SECONDS", "604800"))  # 7 days

# Import apply_openai_proxy_env from Backend/utils.py (without rigid dependence on the package structure))
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
    We take embeddings from Redis cash, otherwise we count through OpenAI embeddings API.
    If there's no key, let's return the None.
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
    Processing of one case
    """
    case_number = case_data.get("case_number", "")
    act_text = case_data.get("act_text", "")
    
    act_text_len = len(act_text) if act_text else 0
    logger.info(f"[PROCESS_CASE_DATA] Case processing {case_number}, query={query}")
    logger.info(f"[PROCESS_CASE_DATA] act_text is present: {bool(act_text)}, length: {act_text_len} Symbols")
    if act_text:
        logger.info(f"[PROCESS_CASE_DATA] The first 300 act_text characters: {act_text[:300]}")
        logger.info(f"[PROCESS_CASE_DATA] The last 300 act_text characters: {act_text[-300:]}")
        if act_text_len < 100:
            logger.error(f"[PROCESS_CASE_DATA] CRITICAL: act_text too short ({act_text_len} Symbols)! LLM will not be able to process!")
    else:
        logger.error(f"[PROCESS_CASE_DATA] CRITICAL: act_text WAY FOR A PROJECT {case_number}!")
    
    # IMPORTANT: Do not launch the Celely group/.get() input within Celery workinger.
    # It's a common cause of grandfathers and timeouts.
    # Instead, agents are performed locally (parallel in flows, as operations I/O-bound)).
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_context = executor.submit(extract_context, case_number, act_text, query)
        f_classification = executor.submit(classify_mention, case_number, act_text, query)

        context_result = f_context.result() or {}
        classification_result = f_classification.result() or {}
        
        logger.info(f"[PROCESS_CASE_DATA] context_result: {context_result}")
        logger.info(f"[PROCESS_CASE_DATA] classification_result: {classification_result}")
    
    # Uniting results
    # Assemble the final record.
    # For TK, the user needs context (fragment) + metadata + reference rather than the entire text of the act.
    processed_case = {**case_data}
    processed_case.pop("act_text", None)  # Not moving on to the full text (database/kash/export)

    # Determine the final type of reference:
    # 1. If there's a classification from LLM, use it
    # 2. If not, but there is type_of_mention from API - translate and use
    # 3. Otherwise, "named person" (by default))
    final_classification = classification_result.get("classification", "")
    api_type = case_data.get("type_of_mention", "")
    
    # If LLM returned "not found" or empty, but there's a type from the API - use translation
    if (not final_classification or final_classification == "не найдено") and api_type:
        # We're going to transfer the type from API to Russian.
        type_translations = {
            "plaintiff": "истец",
            "creditor": "кредитор", 
            "defendant": "ответчик",
            "debtor": "должник",
            "thirdPerson": "третье лицо",
            "other": 'Other person'
        }
        # Take the first type from the list)
        api_type_clean = api_type.split(',')[0].strip()
        final_classification = type_translations.get(api_type_clean, "участник")
    
    # If there is still no classification, use the default "named face"
    if not final_classification or final_classification == "не найдено":
        final_classification = "упомянутое лицо"

    processed_case.update({
        "context": context_result.get("full_context") or context_result.get("context", ""),
        "mentions_count": context_result.get("mentions_count", processed_case.get("metadata", {}).get("mentions_count", 0)),
        "classification": final_classification,  # Use the final classification for API and LLM
        "classification_confidence": classification_result.get("confidence", 0.0),
        # relevance_score is now given a BM25+embeddings hybrid at the batch level (see process_batch))
        "relevance_score": float(case_data.get("_hybrid_score", case_data.get("relevance_score", 0.0)) or 0.0),
        "extraction_confidence": context_result.get("confidence", 0.0),
        "type_of_mention": api_type,  # Save the original type from the API for reference.
    })
    
    return processed_case

@app.task
def process_batch(cases: list, query: str):
    """
    Parallel processing of case boots via Celery
    """
    # Top-N strategy: Fast Sorting for All, LLM for Top-N only.
    # This reduces cost and dramatically improves response time (TH: ≤ 15s)).
    # For default demo/prod script, hold top-N small:
    # Otherwise, even at 89 briefcases and slow proxies, processing can take 10 plus minutes,
    # and upstream (HTTP) would appear to be "perpetual".
    top_n = int(os.getenv("LLM_TOP_N", "5"))
    top_n = max(0, min(top_n, len(cases)))

    # 1) BM25 for all candidates (very cheap)
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

    # (2) Embeddings on top-M on BM25 (limit value)
    # Embeddings – expensive in cold cash. By default limit.
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
                # cosine in [1.1] to [0.1]
                emb_sim[i] = (_cosine(query_emb, e) + 1.0) / 2.0

    # (3) Combination (weight can be sealed)
    w_bm25 = float(os.getenv("WEIGHT_BM25", "0.55"))
    w_emb = float(os.getenv("WEIGHT_EMB", "0.45"))
    base = []
    for i in range(len(cases)):
        # Light Heuristics as Tie-breaker
        heur = _quick_score(cases[i], query) * 0.15
        score = (bm25[i] * w_bm25) + (emb_sim[i] * w_emb) + heur
        score = max(0.0, min(1.0, score))
        cases[i]["_hybrid_score"] = score
        base.append(score)

    # Select top-N for LLM on hybrid score
    idx_sorted2 = sorted(range(len(cases)), key=lambda i: base[i], reverse=True)
    idx_top_n = set(idx_sorted2[:top_n])
    top_cases = [cases[i] for i in idx_sorted2[:top_n]]
    tail_cases = [cases[i] for i in idx_sorted2[top_n:]]

    results = []

    # LLM processing for top-N
    # IMPORTANT: If you process top-N in sequence, the total delay becomes N * (latecy LLM)),
    # which easily turns into 10-15 minutes with proxies/retrays.
    # So let's do parallel case processing (I/O-bound) through the flow pool.
    # Defolt for demo: 8 parallel briefcases (can be redefined env LLM_MAX_WORKERS)
    llm_workers = int(os.getenv("LLM_MAX_WORKERS", "8"))
    llm_workers = max(1, min(llm_workers, max(1, len(top_cases))))
    if top_cases:
        with ThreadPoolExecutor(max_workers=llm_workers) as executor:
            futures = [executor.submit(process_case_data, case, query) for case in top_cases]
            for f in futures:
                try:
                    results.append(f.result())
                except Exception:
                    # fallback: If one case fell, we'll continue anyway.
                    results.append(process_case_data({}, query))

    # The rest are without LLM: use what's already come from API + fast score
    for case in tail_cases:
        processed_case = {**case}
        processed_case.pop("act_text", None)
        processed_case.update({
            "context": processed_case.get("context", ""),
            "mentions_count": processed_case.get("metadata", {}).get("mentions_count", 0),
            "classification": processed_case.get("type_of_mention", "") or 'Reference',
            "classification_confidence": 0.0,
            "relevance_score": float(case.get("_hybrid_score", 0.0) or 0.0),
            "extraction_confidence": 0.0,
        })
        results.append(processed_case)

    return results


if __name__ == "__main__":
    app.start()
