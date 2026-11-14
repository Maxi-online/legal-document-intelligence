from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional, Dict
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, JSON, text, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import base64
from pathlib import Path
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError


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

app = FastAPI(title="Database Service", version="1.0.0")

# Connecting to the database
def _decrypt_settings_payload(payload: Dict, passphrase: str) -> Dict:
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

def _load_settings() -> Dict:
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

def _database_url_from_settings() -> Optional[str]:
    s = _load_settings()
    pg = ((s.get("database") or {}).get("postgres") or {})
    host = pg.get("host")
    port = pg.get("port")
    user = pg.get("user")
    password = pg.get("password")
    db = pg.get("db")
    sslmode = pg.get("sslmode", None)

    if not (host and port and user and password and db):
        return None

    url = f"postgresql://{user}:{password}@{host}:{int(port)}/{db}"
    if sslmode:
        url = f"{url}?sslmode={sslmode}"
    return url

# MANAGEMENT: The main source of the database configuration is settings.json / settings.json.enc.
# Env DATABASE_URL is left only as fallback (for hand override in exceptional cases)).
# The postgres docker network is available on the homename `postgres`. `localhost` inside the container is the container itself.
_db_url_from_settings = _database_url_from_settings()
_db_url_from_env = os.getenv("DATABASE_URL")
_db_url_fallback = os.environ["DB_URL_FALLBACK"]

DATABASE_URL = _db_url_from_settings or _db_url_from_env or _db_url_fallback

# Debugging output for diagnostics
print(f"[database_service] DB URL from settings: {_db_url_from_settings}")
print(f"[database_service] DB URL from env: {_db_url_from_env}")
print(f"[database_service] DB URL fallback: {_db_url_fallback}")
print(f"[database_service] Final DATABASE_URL: {DATABASE_URL[:50]}...")  # First 50 symbols for safety

engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # pool_pre_ping for automatic connection check
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ---- admin auth for dangerous operations (clear DB) ----
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def _jwt_secret_from_settings() -> str:
    s = _load_settings()
    auth = s.get("auth") or {}
    jwt_cfg = auth.get("jwt") or {}
    secret = jwt_cfg.get("secret") or ""
    if not secret:
        raise RuntimeError("Auth secret is not configured in settings.auth.jwt.secret")
    return secret

def require_admin(token: str = Depends(oauth2_scheme)) -> Dict:
    secret = _jwt_secret_from_settings()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        roles = payload.get("roles") or []
        if "admin" not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

class Base(DeclarativeBase):
    pass

# Database models
class Case(Base):
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
    type_of_mention = Column(String, index=True)
    classification = Column(String, index=True)
    relevance_score = Column(Float, index=True)
    extraction_confidence = Column(Float)
    case_metadata = Column(JSON)  # Renamed metadata because metadata is reserved in SQLAlchemy
    created_at = Column(DateTime, default=datetime.now)

class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, index=True)
    query = Column(String)
    search_type = Column(String, index=True)
    total_results = Column(Integer, default=0)
    unique_cases_count = Column(Integer, default=0)
    total_mentions = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending|processing|completed|failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)

# Establishment of tables
Base.metadata.create_all(bind=engine)

# Dependency to receive an database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _parse_date(date_str):
    'Parsing dates from different formats'
    if not date_str:
        return None
    try:
        if "T" in str(date_str):
            # ISO format with time
            date_str = str(date_str).replace("Z", "+00:00")
            return datetime.fromisoformat(date_str)
        else:
            # Date only format
            return datetime.strptime(str(date_str), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None

class SaveResultsRequest(BaseModel):
    task_id: str
    results: List[Dict]

class CreateSearchLogRequest(BaseModel):
    task_id: str
    query: str
    search_type: str
    status: str = "pending"

class UpdateSearchLogRequest(BaseModel):
    task_id: str
    status: str
    total_results: int = 0
    unique_cases_count: int = 0
    total_mentions: int = 0
    duration_ms: int = 0
    error: Optional[str] = None

class ClearDatabaseRequest(BaseModel):
    scope: str = "all"  # "all" | "task"
    task_id: Optional[str] = None
    include_search_logs: bool = True

class ResultResponse(BaseModel):
    id: int
    task_id: str
    case_number: str
    court: str
    date: Optional[datetime]
    act_url: Optional[str]
    parties: Optional[str]
    context: Optional[str]
    type_of_mention: Optional[str]
    classification: Optional[str]
    relevance_score: Optional[float]
    
    class Config:
        from_attributes = True

@app.post("/api/results/save")
async def save_results(request: SaveResultsRequest):
    'Maintaining search results in the database'
    db = SessionLocal()
    try:
        saved_cases = []
        
        for result_data in request.results:
            case = Case(
                task_id=request.task_id,
                case_number=result_data.get("case_number", ""),
                court=result_data.get("court", ""),
                date=_parse_date(result_data.get("date")),
                act_url=result_data.get("act_url", ""),
                parties=", ".join(result_data.get("parties", [])) if isinstance(result_data.get("parties"), list) else result_data.get("parties", ""),
                act_text=result_data.get("act_text", ""),
                act_type=result_data.get("act_type", ""),
                context=result_data.get("context", ""),
                type_of_mention=result_data.get("type_of_mention", ""),
                classification=result_data.get("classification", ""),
                relevance_score=result_data.get("relevance_score", 0.0),
                extraction_confidence=result_data.get("extraction_confidence", 0.0),
                case_metadata=result_data.get("metadata", {}),
            )
            db.add(case)
            saved_cases.append(case)
        
        db.commit()
        
        for case in saved_cases:
            db.refresh(case)
        
        return {
            "status": "success",
            "saved_count": len(saved_cases),
            "task_id": request.task_id
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/search_logs/create")
async def create_search_log(request: CreateSearchLogRequest):
    'Create a search audit record (MLP p.6: logic)'
    db = SessionLocal()
    try:
        log = SearchLog(
            task_id=request.task_id,
            query=request.query,
            search_type=request.search_type,
            status=request.status,
            created_at=datetime.now(),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return {"status": "success", "id": log.id, "task_id": request.task_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/search_logs/update")
async def update_search_log(request: UpdateSearchLogRequest):
    'Update search audit record'
    db = SessionLocal()
    try:
        log = db.query(SearchLog).filter(SearchLog.task_id == request.task_id).order_by(SearchLog.id.desc()).first()
        if not log:
            # If the log is not created (e.g. restarting the service), create on-flight
            log = SearchLog(task_id=request.task_id, query="", search_type="", created_at=datetime.now())
            db.add(log)
            db.flush()

        log.status = request.status
        log.total_results = request.total_results
        log.unique_cases_count = request.unique_cases_count
        log.total_mentions = request.total_mentions
        log.duration_ms = request.duration_ms
        log.error = request.error
        if request.status in ("completed", "failed"):
            log.completed_at = datetime.now()

        db.commit()
        return {"status": "success", "task_id": request.task_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/results/{task_id}")
async def get_results(task_id: str):
    'Results for task_id'
    db = SessionLocal()
    try:
        from sqlalchemy import select
        cases = db.scalars(select(Case).where(Case.task_id == task_id)).all()
        
        if not cases:
            raise HTTPException(status_code=404, detail="Results not found")
        
        results = []
        for case in cases:
            results.append({
                "id": case.id,
                "case_number": case.case_number,
                "court": case.court,
                "date": case.date.isoformat() if case.date else None,
                "ingested_at": case.created_at.isoformat() if case.created_at else None,
                "act_url": case.act_url,
                "parties": case.parties,
                "context": case.context,
                "type_of_mention": case.type_of_mention,
                "classification": case.classification,
                "relevance_score": case.relevance_score,
                "act_type": case.act_type,
                "metadata": case.case_metadata or {},
            })
        
        # Counting of unique cases and references (T3.4)
        unique_cases = set()
        total_mentions = len(cases)
        
        for case in cases:
            if case.case_number:
                unique_cases.add(case.case_number)
        
        # Sorting by date (new above) and relevance (T3.3))
        results.sort(key=lambda x: (
            x.get("date") or "",  # By date (new above - desc)
            -(x.get("relevance_score") or 0.0)  # Relevant (above - desc)
        ), reverse=True)
        
        return {
            "task_id": task_id,
            "results": results,
            "total": len(results),
            "unique_cases_count": len(unique_cases),
            "total_mentions": total_mentions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/admin/clear")
async def clear_database(request: ClearDatabaseRequest, _: Dict = Depends(require_admin)):
    """
    Dangerous operation: PostgreSQL clean-up.
    Only admin is available (JWT rolls include "admin").
    """
    if request.scope not in ("all", "task"):
        raise HTTPException(status_code=400, detail="Invalid scope. Use: all|task")
    if request.scope == "task" and not request.task_id:
        raise HTTPException(status_code=400, detail="task_id is required for scope=task")

    db = SessionLocal()
    try:
        deleted_cases = 0
        deleted_logs = 0

        if request.scope == "all":
            deleted_cases = db.query(Case).delete(synchronize_session=False)
            if request.include_search_logs:
                deleted_logs = db.query(SearchLog).delete(synchronize_session=False)
        else:
            deleted_cases = db.query(Case).filter(Case.task_id == request.task_id).delete(synchronize_session=False)
            if request.include_search_logs:
                deleted_logs = db.query(SearchLog).filter(SearchLog.task_id == request.task_id).delete(synchronize_session=False)

        db.commit()
        return {"status": "success", "deleted_cases": int(deleted_cases), "deleted_search_logs": int(deleted_logs)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/results")
async def search_results(
    court: Optional[str] = None,
    classification: Optional[str] = None,
    min_relevance: Optional[float] = None,
    limit: int = 100
):
    'Searching for filter results'
    db = SessionLocal()
    try:
        from sqlalchemy import select
        query = select(Case)
        
        if court:
            query = query.where(Case.court.contains(court))
        if classification:
            query = query.where(Case.classification == classification)
        if min_relevance is not None:
            query = query.where(Case.relevance_score >= min_relevance)
        
        query = query.order_by(Case.relevance_score.desc()).limit(limit)
        cases = db.scalars(query).all()
        
        results = []
        for case in cases:
            results.append({
                "id": case.id,
                "task_id": case.task_id,
                "case_number": case.case_number,
                "court": case.court,
                "date": case.date.isoformat() if case.date else None,
                "act_url": case.act_url,
                "parties": case.parties,
                "context": case.context,
                "type_of_mention": case.type_of_mention,
                "classification": case.classification,
                "relevance_score": case.relevance_score,
            })
        
        return {
            "results": results,
            "total": len(results)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/health")
async def health():
    'Service health check'
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "healthy", "service": "database_service"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
