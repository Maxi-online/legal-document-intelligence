from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import httpx
import uuid
from datetime import datetime
import os
from dotenv import load_dotenv
import time
from pathlib import Path
import io
import zipfile
import json
import base64
import httpx
import logging


def _resolve_settings_env(value):
    """Resolve required environment references in already parsed configuration."""
    import os
    import re
    if isinstance(value, dict):
        return {key: _resolve_settings_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_settings_env(item) for item in value]
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\$\{([A-Z_][A-Z0-9_]*)(?::(int|float|bool))?\}", value)
    if match is None:
        return value
    name, kind = match.groups()
    content = os.environ.get(name)
    if content is None or not content.strip():
        raise RuntimeError(f"Required configuration variable is missing: {name}")
    if kind == "int":
        return int(content)
    if kind == "float":
        return float(content)
    if kind == "bool":
        if content.lower() not in {"true", "false", "1", "0"}:
            raise ValueError(f"Expected a boolean configuration variable: {name}")
        return content.lower() in {"true", "1"}
    return content



load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DocumentIntelligence API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URLs микросервисов
CASEBOOK_API_SERVICE_URL = os.getenv("CASEBOOK_API_SERVICE_URL", "http://localhost:8001")
DATA_PROCESSING_SERVICE_URL = os.getenv("DATA_PROCESSING_SERVICE_URL", "http://localhost:8002")
DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://localhost:8003")
FILE_EXPORT_SERVICE_URL = os.getenv("FILE_EXPORT_SERVICE_URL", "http://localhost:8004")
CACHE_SERVICE_URL = os.getenv("CACHE_SERVICE_URL", "http://localhost:8005")

# Таймауты для вызова data_processing.
# Важно: если передать в httpx timeout как число, оно применяется и к connect timeout.
# Это приводит к "вечному ожиданию" при проблемах DNS/сети между контейнерами.
DATA_PROCESSING_READ_TIMEOUT_SECONDS = float(os.getenv("DATA_PROCESSING_HTTP_TIMEOUT_SECONDS", "1200"))
DATA_PROCESSING_CONNECT_TIMEOUT_SECONDS = float(os.getenv("DATA_PROCESSING_CONNECT_TIMEOUT_SECONDS", "10"))
DATA_PROCESSING_TIMEOUT = httpx.Timeout(
    connect=DATA_PROCESSING_CONNECT_TIMEOUT_SECONDS,
    read=DATA_PROCESSING_READ_TIMEOUT_SECONDS,
    write=30.0,
    pool=10.0,
)

# ---------- Auth (JWT) ----------
# ВАЖНО: api_gateway в контейнере не имеет доступа к `backend/utils.py`,
# поэтому загрузку settings делаем локально (settings.json / settings.json.enc).
def _decrypt_settings_payload(payload: Dict[str, Any], passphrase: str) -> Dict[str, Any]:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.fernet import Fernet

    v = int(payload.get("v", 0))
    if v != 1:
        raise ValueError("Unsupported settings encryption version")

    salt_b64 = payload.get("salt")
    token_b64 = payload.get("token")
    iters = int(payload.get("iter", 200000))
    if not salt_b64 or not token_b64:
        raise ValueError("Invalid encrypted settings payload (missing salt/token)")

    salt = base64.b64decode(salt_b64)
    token = base64.b64decode(token_b64)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iters,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    f = Fernet(key)
    plaintext = f.decrypt(token)
    return _resolve_settings_env(json.loads(plaintext.decode("utf-8")))

def load_settings() -> Dict[str, Any]:
    """
    Загружает settings из одного из путей:
    - /settings.json.enc (в docker-compose монтируется сюда)
    - /settings.json
    - ./settings.json.enc / ./settings.json (локальный запуск)
    """
    possible_enc = [
        Path("/settings.json.enc"),
        Path("/app/settings.json.enc"),
        Path(__file__).resolve().parent.parent.parent / "settings.json.enc",
    ]
    for p in possible_enc:
        if p.exists():
            passphrase = os.getenv("SETTINGS_PASSPHRASE", "")
            if not passphrase:
                raise RuntimeError("SETTINGS_PASSPHRASE is required to decrypt settings.json.enc")
            payload = _resolve_settings_env(json.loads(p.read_text(encoding="utf-8-sig")))
            return _decrypt_settings_payload(payload, passphrase)

    possible_plain = [
        Path("/settings.json"),
        Path("/app/settings.json"),
        Path(__file__).resolve().parent.parent.parent / "settings.json",
    ]
    for p in possible_plain:
        if p.exists():
            return _resolve_settings_env(json.loads(p.read_text(encoding="utf-8-sig")))

    return {}

import bcrypt
from jose import jwt, JWTError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def _auth_settings() -> Dict[str, Any]:
    settings = load_settings()
    auth = settings.get("auth") or {}
    jwt_cfg = auth.get("jwt") or {}
    users = auth.get("users") or []
    secret = jwt_cfg.get("secret") or ""
    ttl = int(jwt_cfg.get("access_token_ttl_minutes", 60))
    if not secret:
        raise RuntimeError("Auth is not configured: settings.auth.jwt.secret is empty")
    return {"secret": secret, "ttl": ttl, "users": users}

def _find_user(username: str) -> Optional[Dict[str, Any]]:
    cfg = _auth_settings()
    for u in cfg["users"]:
        if isinstance(u, dict) and u.get("username") == username:
            return u
    return None

def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def _create_access_token(username: str, roles: List[str]) -> Dict[str, Any]:
    cfg = _auth_settings()
    now = int(time.time())
    exp = now + int(cfg["ttl"]) * 60
    token = jwt.encode(
        {"sub": username, "roles": roles, "iat": now, "exp": exp},
        cfg["secret"],
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": int(cfg["ttl"]) * 60}

def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    cfg = _auth_settings()
    try:
        if not token:
            print("[get_current_user] Токен отсутствует")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing")
        print(f"[get_current_user] Получен токен: {token[:20]}...")
        payload = jwt.decode(token, cfg["secret"], algorithms=["HS256"])
        username = payload.get("sub")
        roles = payload.get("roles") or []
        if not username:
            print(f"[get_current_user] Токен не содержит username: {payload}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        print(f"[get_current_user] Успешная авторизация: username={username}, roles={roles}")
        return {"username": username, "roles": roles}
    except JWTError as e:
        print(f"[get_current_user] JWTError: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception as e:
        print(f"[get_current_user] Исключение: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    roles = current_user.get("roles") or []
    if "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user

TASK_STATUS_TTL_SECONDS = int(os.getenv("TASK_STATUS_TTL_SECONDS", "604800"))  # 7 суток по ТЗ (retention)

# In-memory fallback (используем только если cache_service недоступен)
task_status = {}

async def _set_task_status(task_id: str, status_payload: dict):
    """
    Сохраняем статус задачи в cache_service (Redis), чтобы переживать рестарты gateway.
    Best-effort: при ошибке падаем обратно на in-memory.
    """
    task_status[task_id] = status_payload
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{CACHE_SERVICE_URL}/cache/set",
                json={
                    "key": f"task_status:{task_id}",
                    "value": status_payload,
                    "ttl": TASK_STATUS_TTL_SECONDS,
                },
            )
    except Exception:
        pass

from typing import Optional, Dict, Any

async def _get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Читаем статус задачи из cache_service (Redis)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{CACHE_SERVICE_URL}/cache/get",
                params={"key": f"task_status:{task_id}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("cached"):
                    return data.get("value")
    except Exception:
        pass
    return task_status.get(task_id)

class SearchRequest(BaseModel):
    query: str
    search_type: str  # "fio", "inn", "company"

class TaskStatus(BaseModel):
    task_id: str
    status: str  # "pending", "processing", "completed", "failed"
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
async def login(request: LoginRequest):
    user = _find_user(request.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    hashed = user.get("password_bcrypt") or ""
    if not hashed or not _verify_password(request.password, hashed):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    roles = user.get("roles") or ["user"]
    return _create_access_token(request.username, roles)

@app.get("/api/auth/me")
async def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return current_user

@app.get("/api/acts/{act_id}/download")
async def download_act(act_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Proxy скачивания одного акта через Casebook API Service.
    В моковом режиме pravo_api_service отдаёт текстовый файл.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(f"{CASEBOOK_API_SERVICE_URL}/api/acts/{act_id}/download")

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Failed to download act")

    content_type = resp.headers.get("content-type", "application/octet-stream")
    content_disp = resp.headers.get("content-disposition", f'attachment; filename="act_{act_id}"')
    return Response(content=resp.content, media_type=content_type, headers={"Content-Disposition": content_disp})

@app.get("/api/acts/download_all/{task_id}")
async def download_all_acts(task_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Скачивает все акты по задаче и возвращает ZIP.
    Если какой-то акт недоступен, кладём в архив .txt с ошибкой/ссылкой.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        db_response = await client.get(f"{DATABASE_SERVICE_URL}/api/results/{task_id}", timeout=30.0)
        if db_response.status_code != 200:
            raise HTTPException(status_code=404, detail="Results not found")
        results_data = db_response.json()

    results = results_data.get("results", []) or []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for idx, r in enumerate(results, 1):
                if not isinstance(r, dict):
                    continue
                act_url = (r.get("act_url") or "").strip()
                case_number = (r.get("case_number") or "").replace("/", "-")
                filename_base = f"{idx:03d}_{case_number}" if case_number else f"{idx:03d}_act"

                if not act_url:
                    zf.writestr(f"{filename_base}.txt", "Missing act_url")
                    continue

                try:
                    resp = await client.get(act_url, follow_redirects=True)
                    if resp.status_code != 200:
                        raise RuntimeError(f"HTTP {resp.status_code}")

                    # filename from content-disposition if present
                    cd = resp.headers.get("content-disposition", "")
                    out_name = None
                    if "filename=" in cd:
                        out_name = cd.split("filename=")[-1].strip().strip("\"'")
                    if not out_name:
                        # fallback: guess extension from content-type
                        ct = resp.headers.get("content-type", "")
                        ext = "bin"
                        if "text/plain" in ct:
                            ext = "txt"
                        elif "pdf" in ct:
                            ext = "pdf"
                        out_name = f"{filename_base}.{ext}"

                    zf.writestr(out_name, resp.content)
                except Exception as e:
                    zf.writestr(
                        f"{filename_base}_ERROR.txt",
                        f"Failed to download: {act_url}\nError: {e}\nContext: {(r.get('context') or '')[:500]}",
                    )

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="document_intelligence_acts_{task_id}.zip"'},
    )

class ClearDatabaseRequest(BaseModel):
    scope: str = "all"  # "all" | "task"
    task_id: Optional[str] = None
    include_search_logs: bool = True

@app.post("/api/admin/clear")
async def admin_clear_database(request: ClearDatabaseRequest, current_user: Dict[str, Any] = Depends(require_admin), token: str = Depends(oauth2_scheme)):
    """
    Proxy к database_service: очистка БД по кнопке.
    Требует admin и передаёт JWT в database_service для авторизации.
    """
    print(f"[admin_clear_database] Запрос от пользователя: {current_user.get('username')}, роли: {current_user.get('roles')}")
    print(f"[admin_clear_database] Параметры: scope={request.scope}, task_id={request.task_id}, include_search_logs={request.include_search_logs}")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{DATABASE_SERVICE_URL}/api/admin/clear",
                json=request.model_dump(),
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code != 200:
            print(f"[admin_clear_database] Ошибка от database_service: {resp.status_code} - {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        result = resp.json()
        print(f"[admin_clear_database] База успешно очищена: {result}")
        return result
    except Exception as e:
        print(f"[admin_clear_database] Исключение: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/cache/clear")
async def admin_clear_cache(current_user: Dict[str, Any] = Depends(require_admin)):
    """
    Очистка Redis кэша (flushdb) через cache_service.
    Требует роль admin.
    """
    print(f"[admin_clear_cache] Запрос от пользователя: {current_user.get('username')}, роли: {current_user.get('roles')}")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{CACHE_SERVICE_URL}/cache/clear")
        if resp.status_code != 200:
            print(f"[admin_clear_cache] Ошибка от cache_service: {resp.status_code} - {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        result = resp.json()
        print(f"[admin_clear_cache] Кэш успешно очищен: {result}")
        return result
    except Exception as e:
        print(f"[admin_clear_cache] Исключение: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search(request: SearchRequest, background_tasks: BackgroundTasks, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Создать задачу на поиск судебных актов"""
    task_id = str(uuid.uuid4())
    cache_key = f"search:{request.search_type}:{request.query}"
    
    await _set_task_status(task_id, {
        "status": "pending",
        "created_at": datetime.now(),
        "completed_at": None,
        "error": None,
        "cache_key": cache_key,
    })
    
    # Запускаем обработку в фоне
    background_tasks.add_task(process_search_task, task_id, request)
    
    return {"task_id": task_id, "status": "pending"}

async def process_search_task(task_id: str, request: SearchRequest):
    """Асинхронная обработка задачи поиска"""
    started = time.perf_counter()
    try:
        print(f"[{task_id}] Начало обработки задачи поиска: {request.query}")
        current = await _get_task_status(task_id) or {}
        current.update({"status": "processing"})
        await _set_task_status(task_id, current)
        cache_key = current.get("cache_key") or f"search:{request.search_type}:{request.query}"

        # Поддержка нескольких запросов через запятую (ТЗ п.3.1)
        queries = [q.strip() for q in (request.query or "").split(",") if q.strip()]
        if not queries:
            queries = [request.query]

        # Логируем старт запроса (не критично при ошибке)
        try:
            async with httpx.AsyncClient(timeout=5.0) as log_client:
                await log_client.post(
                    f"{DATABASE_SERVICE_URL}/api/search_logs/create",
                    json={
                        "task_id": task_id,
                        "query": request.query,
                        "search_type": request.search_type,
                        "status": "processing",
                    },
                )
        except Exception as log_err:
            print(f"[{task_id}] Failed to create search log: {log_err}")
        
        # Проверяем кэш (пропускаем при ошибках подключения)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                cache_response = await client.get(
                    f"{CACHE_SERVICE_URL}/cache/get",
                    params={"key": cache_key}
                )
                
                if cache_response.status_code == 200:
                    cached_data = cache_response.json()
                    if cached_data.get("cached"):
                        cached_value = cached_data.get("value") or {}

                        # Критично: при cache-hit нужно либо вернуть данные из кэша,
                        # либо сохранить их в БД под новый task_id — иначе /results и экспорт сломаются.
                        try:
                            await client.post(
                                f"{DATABASE_SERVICE_URL}/api/results/save",
                                json={
                                    "task_id": task_id,
                                    "results": cached_value.get("results", []),
                                },
                                timeout=30.0
                            )
                        except Exception as db_cache_save_error:
                            print(f"[{task_id}] Failed to persist cached results to DB: {db_cache_save_error}")

                        task_status[task_id]["status"] = "completed"
                        current = await _get_task_status(task_id) or {}
                        current.update({"status": "completed", "completed_at": datetime.now(), "error": None})
                        await _set_task_status(task_id, current)

                        # обновляем аудит-лог (best-effort)
                        try:
                            duration_ms = int((time.perf_counter() - started) * 1000)
                            await client.post(
                                f"{DATABASE_SERVICE_URL}/api/search_logs/update",
                                json={
                                    "task_id": task_id,
                                    "status": "completed",
                                    "total_results": len(cached_value.get("results", []) if isinstance(cached_value, dict) else []),
                                    "unique_cases_count": 0,
                                    "total_mentions": len(cached_value.get("results", []) if isinstance(cached_value, dict) else []),
                                    "duration_ms": duration_ms,
                                },
                                timeout=5.0
                            )
                        except Exception:
                            pass
                        return
        except Exception as cache_error:
            # Продолжаем без кэша при ошибке подключения
            print(f"Cache service unavailable, continuing without cache: {cache_error}")
            pass
        
        # Получаем данные из Casebook API (по каждому подзапросу)
        async with httpx.AsyncClient() as client:
            aggregated_results = []

            for q in queries:
                per_query_cache_key = f"search:{request.search_type}:{q}"

                # Пытаемся взять готовый результат из кэша для подзапроса
                per_cached = None
                try:
                    per_cache_resp = await client.get(
                        f"{CACHE_SERVICE_URL}/cache/get",
                        params={"key": per_query_cache_key},
                        timeout=5.0
                    )
                    if per_cache_resp.status_code == 200:
                        per_cache_json = per_cache_resp.json()
                        if per_cache_json.get("cached"):
                            per_cached = per_cache_json.get("value") or {}
                except Exception:
                    per_cached = None

                if per_cached and isinstance(per_cached, dict) and per_cached.get("results") is not None:
                    per_results = per_cached.get("results", [])
                    # КРИТИЧНО: Результаты из кэша БЕЗ act_text - нужно загрузить полный текст для LLM
                    # Загружаем act_text через pravo_api_service для каждого результата
                    for r in per_results:
                        if isinstance(r, dict):
                            meta = dict(r.get("metadata") or {})
                            meta["source_query"] = q
                            r["metadata"] = meta
                            # Загружаем полный текст документа для LLM обработки
                            case_id = meta.get("case_id")
                            document_id = meta.get("document_id")
                            if case_id and document_id and not r.get("act_text"):
                                try:
                                    enrich_response = await client.post(
                                        f"{CASEBOOK_API_SERVICE_URL}/api/enrich",
                                        json={"case_id": case_id, "document_id": document_id},
                                        timeout=30.0
                                    )
                                    if enrich_response.status_code == 200:
                                        enrich_data = enrich_response.json()
                                        r["act_text"] = enrich_data.get("act_text", "")
                                except Exception as enrich_err:
                                    logger.warning(f"[{task_id}] Не удалось загрузить act_text для {case_id}/{document_id}: {enrich_err}")
                    aggregated_results.extend(per_results)
                    continue

                # Запрашиваем данные из Casebook API
                casebook_response = await client.post(
                    f"{CASEBOOK_API_SERVICE_URL}/api/search",
                    json={"query": q, "search_type": request.search_type},
                    timeout=60.0
                )

                if casebook_response.status_code != 200:
                    raise Exception(f"Casebook API error: {casebook_response.text}")

                casebook_data = casebook_response.json()
                casebook_results = casebook_data.get('results', [])
                logger.info(f"[{task_id}] Получено результатов из Casebook API для '{q}': {len(casebook_results)}")
                print(f"[{task_id}] Получено результатов из Casebook API для '{q}': {len(casebook_results)}")
                
                # КРИТИЧНО: Проверяем наличие act_text в результатах ДО отправки в data_processing
                for idx, result in enumerate(casebook_results):
                    act_text = result.get('act_text', '')
                    case_number = result.get('case_number', 'unknown')
                    logger.info(f"[{task_id}] Результат {idx} ({case_number}): act_text присутствует={bool(act_text)}, длина={len(act_text) if act_text else 0}")
                    print(f"[{task_id}] Результат {idx} ({case_number}): act_text присутствует={bool(act_text)}, длина={len(act_text) if act_text else 0}")
                    if not act_text:
                        logger.error(f"[{task_id}] КРИТИЧНО: Результат {idx} ({case_number}): act_text ОТСУТСТВУЕТ! LLM не сможет обработать это дело!")
                        print(f"[{task_id}] КРИТИЧНО: Результат {idx} ({case_number}): act_text ОТСУТСТВУЕТ! LLM не сможет обработать это дело!")
                    elif len(act_text) < 100:
                        logger.warning(f"[{task_id}] Результат {idx} ({case_number}): act_text слишком короткий ({len(act_text)} символов), возможно это не полный текст")
                        print(f"[{task_id}] Результат {idx} ({case_number}): act_text слишком короткий ({len(act_text)} символов), возможно это не полный текст")
                    else:
                        logger.info(f"[{task_id}] Результат {idx} ({case_number}): первые 200 символов act_text: {act_text[:200]}")
                        print(f"[{task_id}] Результат {idx} ({case_number}): первые 200 символов act_text: {act_text[:200]}")

                # Отправляем на обработку данных
                print(f"[{task_id}] Отправка запроса на обработку данных в {DATA_PROCESSING_SERVICE_URL}/api/process (query='{q}')")
                try:
                    import traceback
                    processing_response = await client.post(
                        f"{DATA_PROCESSING_SERVICE_URL}/api/process",
                        json={
                            "task_id": task_id,
                            "data": {"results": casebook_results},
                            "query": q,
                        },
                        timeout=DATA_PROCESSING_TIMEOUT
                    )
                except Exception as proc_error:
                    error_traceback = traceback.format_exc()
                    print(f"[{task_id}] ОШИБКА при запросе к data_processing (query='{q}'): {proc_error}")
                    print(f"[{task_id}] Traceback: {error_traceback}")
                    raise

                if processing_response.status_code != 200:
                    raise Exception(f"Data processing error: {processing_response.text}")

                per_processing_result = processing_response.json() or {}
                per_results = per_processing_result.get("results", [])
                for r in per_results:
                    if isinstance(r, dict):
                        meta = dict(r.get("metadata") or {})
                        meta["source_query"] = q
                        r["metadata"] = meta
                aggregated_results.extend(per_results)

                # Кэшируем результат конкретного подзапроса (БЕЗ act_text - он слишком большой)
                try:
                    safe_results = []
                    for r in per_results:
                        if not isinstance(r, dict):
                            continue
                        safe_r = dict(r)
                        safe_r.pop("act_text", None)  # Не храним полный текст в кэше
                        safe_results.append(safe_r)
                    await client.post(
                        f"{CACHE_SERVICE_URL}/cache/set",
                        json={
                            "key": per_query_cache_key,
                            "value": {"results": safe_results, "total": len(safe_results)},
                            "ttl": 3600
                        },
                        timeout=5.0
                    )
                except Exception:
                    pass

            processing_result = {"task_id": task_id, "results": aggregated_results, "status": "completed"}
            print(f"[{task_id}] Агрегация завершена, всего результатов: {len(processing_result.get('results', []))}")
            
            # Фильтрация дубликатов:
            # по ТЗ мы не должны терять несколько актов в одном деле,
            # поэтому дедуплицируем по акту (URL), а не по номеру дела.
            unique_acts = {}
            for result in processing_result.get("results", []):
                act_url = (result.get("act_url") or "").strip()
                fallback_key = f"{result.get('case_number','')}|{result.get('date','')}|{result.get('act_type','')}"
                key = act_url or fallback_key

                if key not in unique_acts:
                    unique_acts[key] = result
                else:
                    existing = unique_acts[key]
                    if (result.get("relevance_score", 0.0) or 0.0) > (existing.get("relevance_score", 0.0) or 0.0):
                        unique_acts[key] = result
            
            processing_result["results"] = list(unique_acts.values())
            
            # Сохраняем в базу данных
            await client.post(
                f"{DATABASE_SERVICE_URL}/api/results/save",
                json={
                    "task_id": task_id,
                    "results": processing_result.get("results", []),
                },
                timeout=30.0
            )

            # Получаем агрегированные счетчики (unique cases / total mentions) и пишем в аудит-лог
            unique_cases_count = 0
            try:
                unique_cases = set()
                for r in processing_result.get("results", []):
                    if isinstance(r, dict) and r.get("case_number"):
                        unique_cases.add(r.get("case_number"))
                unique_cases_count = len(unique_cases)
            except Exception:
                unique_cases_count = 0
            
            # Кэшируем результат (БЕЗ act_text - он слишком большой для кэша)
            try:
                safe_results = []
                for r in processing_result.get("results", []):
                    if not isinstance(r, dict):
                        continue
                    safe_r = dict(r)
                    safe_r.pop("act_text", None)  # Не храним полный текст в кэше
                    safe_results.append(safe_r)
                await client.post(
                    f"{CACHE_SERVICE_URL}/cache/set",
                    json={
                        "key": cache_key,
                        "value": {**processing_result, "results": safe_results},
                        "ttl": 3600
                    },
                    timeout=5.0
                )
            except Exception as cache_error:
                print(f"Failed to cache result: {cache_error}")
                pass
            
            task_status[task_id]["status"] = "completed"
            current = await _get_task_status(task_id) or {}
            current.update({"status": "completed", "completed_at": datetime.now(), "error": None})
            await _set_task_status(task_id, current)
            print(f"[{task_id}] Задача успешно завершена")

            try:
                duration_ms = int((time.perf_counter() - started) * 1000)
                await client.post(
                    f"{DATABASE_SERVICE_URL}/api/search_logs/update",
                    json={
                        "task_id": task_id,
                        "status": "completed",
                        "total_results": len(processing_result.get("results", [])),
                        "unique_cases_count": unique_cases_count,
                        "total_mentions": len(processing_result.get("results", [])),
                        "duration_ms": duration_ms,
                    },
                    timeout=5.0
                )
            except Exception as log_err:
                print(f"[{task_id}] Failed to update search log: {log_err}")
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        print(f"Error in process_search_task for task {task_id}: {error_msg}")
        print(f"Traceback: {error_traceback}")
        current = await _get_task_status(task_id) or {}
        current.update({"status": "failed", "error": error_msg, "completed_at": datetime.now()})
        await _set_task_status(task_id, current)

        # best-effort аудит-лог
        try:
            duration_ms = int((time.perf_counter() - started) * 1000)
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{DATABASE_SERVICE_URL}/api/search_logs/update",
                    json={
                        "task_id": task_id,
                        "status": "failed",
                        "total_results": 0,
                        "unique_cases_count": 0,
                        "total_mentions": 0,
                        "duration_ms": duration_ms,
                        "error": error_msg,
                    },
                )
        except Exception:
            pass

@app.get("/api/search/status/{task_id}")
async def get_search_status(task_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Получить статус задачи поиска"""
    status_data = await _get_task_status(task_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task_id,
        "status": status_data["status"],
        "created_at": status_data["created_at"].isoformat(),
        "completed_at": status_data["completed_at"].isoformat() if status_data["completed_at"] else None,
        "error": status_data.get("error"),
    }

@app.get("/api/search/results/{task_id}")
async def get_search_results(task_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Получить результаты поиска"""
    status_data = await _get_task_status(task_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Task not found")
    if status_data["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed yet")
    
    # Получаем результаты из базы данных
    async with httpx.AsyncClient() as client:
        db_response = await client.get(
            f"{DATABASE_SERVICE_URL}/api/results/{task_id}",
            timeout=30.0
        )
        
        if db_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Error retrieving results")
        
        return db_response.json()

@app.get("/api/export/{task_id}")
async def export_results(task_id: str, format: str = "excel", current_user: Dict[str, Any] = Depends(get_current_user)):
    """Экспортировать результаты в файл"""
    if format not in ["excel", "pdf", "json"]:
        raise HTTPException(status_code=400, detail="Invalid format. Use: excel, pdf, or json")
    
    # Получаем результаты из базы данных
    async with httpx.AsyncClient() as client:
        db_response = await client.get(
            f"{DATABASE_SERVICE_URL}/api/results/{task_id}",
            timeout=30.0
        )
        
        if db_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Error retrieving results")
        
        results_data = db_response.json()
        
        # Экспортируем через File Export Service
        export_response = await client.post(
            f"{FILE_EXPORT_SERVICE_URL}/api/export",
            json={
                "task_id": task_id,
                "format": format,
                "data": results_data.get("results", []),
            },
            timeout=60.0
        )
        
        if export_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Error exporting results")
        
        from fastapi.responses import Response
        
        # Возвращаем ответ напрямую от File Export Service
        content_type = export_response.headers.get("content-type", "application/octet-stream")
        content_disposition = export_response.headers.get("content-disposition", 
            f'attachment; filename="document_intelligence_results_{task_id}.{format if format != "excel" else "xlsx"}"')
        
        return Response(
            content=export_response.content,
            media_type=content_type,
            headers={"Content-Disposition": content_disposition}
        )

@app.get("/api/translations")
async def get_translations():
    """Получение переводов для фронтенда"""
    import json
    from pathlib import Path
    
    # Ищем файл переводов в разных местах
    possible_paths = [
        Path("/app/backend/utils/translations.json"),
        Path(__file__).parent.parent / "utils" / "translations.json",
        Path(__file__).parent.parent.parent / "backend" / "utils" / "translations.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return _resolve_settings_env(json.load(f))
            except Exception as e:
                print(f"Error loading translations from {path}: {e}")
    
    # Fallback: возвращаем базовые переводы
    return {
        "side_types": {
            "plaintiff": "истец",
            "creditor": "кредитор",
            "defendant": "ответчик",
            "debtor": "должник",
            "thirdPerson": "третье лицо",
            "other": "иное лицо",
            "all": "все"
        },
        "classification_types": {
            "участник": "Участник дела",
            "упомянутое лицо": "Упомянутое лицо",
            "контрагент": "Контрагент",
            "аффилированное лицо": "Аффилированное лицо",
            "истец": "Истец",
            "ответчик": "Ответчик",
            "третье лицо": "Третье лицо",
            "кредитор": "Кредитор",
            "должник": "Должник",
            "не найдено": "Не найдено",
            "не определено": "Не определено"
        }
    }

@app.get("/health")
async def health():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "api_gateway"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
