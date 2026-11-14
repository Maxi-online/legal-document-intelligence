# DocumentIntelligence

## Engineering review

Micro-service search and processing system of legal documents: gateway, source integration, extract and ranking, task line, PostgreSQL, Redis and export results. External moss allows the integration contract to be reviewed separately from real access.

### Code navigation

- [backend/api_gateway/main.py](../backend/api_gateway/main.py)
- [backend/data_processing_services/orchestrator.py](../backend/data_processing_services/orchestrator.py)
- [backend/pravo_tech_casebook_api_service/mock_data.py](../backend/pravo_tech_casebook_api_service/mock_data.py)
- [docker-compose.yml](../docker-compose.yml)

### Reproduction and evaluation

Check the search, extract and correctness of the links on the permitted corner with the tag. External API's wet response does not confirm the availability of a real source and the completeness of the legal study. Productivity, LLM cost and response quality are measured separately.


Service for **seeking references of natural and legal persons in legal proceedings** through the corporate Casebook/PravoTech API (and/or mouth mode), in order to show:

- ** Where the person is a party;**
- **acts in which a person is mentioned in the text** even if he or she is not a party to the case;
- ** Context of reference**, type/role and reference to act;
- Export results in **Excel/PDF/JSON**.

The project fulfils the requirements of TK . . . Search for references to natural and legal persons in court acts through API Right”.

## Key opportunities

- **Introduction**: FIO / INS / name of turf; supported ** by a few requests by a comma**.
- **Full text search**: via `pravo_tech_casebook_api_service` service (real API or moss – data)).
- ** Post-treatment**:
  - deduplication by `act_url` (to avoid losing different acts of one case));
  - ranking **BM25 + embeddings** + heuristics;
  - LLM – Processing (context/role) ** only for top –N** acts.
- **Storage**: PostgreSQL).
- **Cash**: Redis (cash issuance, tasks status, embeddings with TTL).
- **UI**: Results table, filters, line lighting, export.

## Architecture (microservices)

- **`frontend/`** (React + Vite): UI
- **`Backend/api_gateway/'** (FastAPI): Single Entry Point, Task Status, Aggregation
- **`Backend/pravo_tech_casebook_api_service/'** (FastAPI): adapter to Casebook API + wet mode
- **`Backend/data_processing_services/'** (FastAPI + Celery): ranking and top –N LLM processing
- **`backend/database_service/`** (FastAPI + SQLAlchemy): PostgreSQL, results and audit‑log(`search_logs`)
- **`Backend/cache_service/'** (FastAPI + Redis): Cash values, task status, embedding cache
- **`Backend/file_export_service/'** (FastAPI): Excel/PDF/JSON export

## Quick start (Docker Compose)

Requirements: Docker + Docker Compase.

Launch:

```bash
docker-compose up -d --build
```

Address:

- **Frontend**: `http://localhost:3000`
- **API Gateway**: `http://localhost:8000`
- **Casebook API Service**: `http://localhost:8001`
- **Data Processing Service**: `http://localhost:8002`
- **Database Service**: `http://localhost:8003`
- **File Export Service**: `http://localhost:8004`
- **Cache Service**: `http://localhost:8005`

## Settings (secrets and parameters)

### Recommended method: environmental variables

- **`OPENAI_API_KEY'**: key for LLM and embeddings (if not specified - the system works but no embedding/LLM – improvements)
- **`CASEBOOK_API_KEY'**: Casebook API key (if not specified, wet mode on))
- **`CASEBOOK_BASE_URL'**: Core URL Casebook API)

### Alternative: `settings.json`

See `settings.json.example`. If `casebook.api_key` is empty or equal to default value, wet mode shall be used.

## Moist mode (demo/test)

If `CASEBOOK_API_KEY` is missing (or `settings.json` without key), the service automatically uses moc – data.

Moki include:

- fixed scenarios (claimer/defendant/third person/contractor/remark));
- **scale set** (thousands/hundreds of acts) with different ships/data/types of acts, writing options and control duplicates.

Parameters:

- **`MOCK_RESULTS_COUNT'**: wet delivery size (20.250), default 80.

Details: `MOCK_API_GUIDE.md` and `backend/pravo_tech_casebook_api_service/README_MOCK.md`.

## API (main)

### API Gateway (`http://localhost:8000`)

- **`POST /api/search`**: Create search task
  - `query': string, allows several values through a comma
  - `search_type`: `fio | inn | company`
- **`GET /api/search/status/{task_id}'**: Task status (stats stored in Redis with TTL 7 days)
- **`GET /api/search/results/{task_id}`**: results+ metering(`total`, `unique_cases_count`, `total_mentions`)
- **`GET /api/export/{task_id}?format=excel

### Healthchecks

Each service has **`GET /health`**.

## Productivity and tuning

Key parameters:

- **`LLM_TOP_N'** (default 20): how many acts to send to LLM – processing
- **`EMBED_TOP_M`** (default 80): how many acts by BM25 are enriched by embeddings
- **`WEIGHT_BM25`** / **`WEIGHT_EMB`**: Hybrid ranking weight

Objective: To fit in with a reasonable number of candidates.

## Data security and storage

- **Acts** should not be cashed unlimited: cash/embeddings are set to **TTL 7 days**.
- The status of the task is in Redis with TTL (7 days default).
- It is recommended to store keys through env/Secret Manager and not communicate secrets.

## Development without Docker (Windows / PowerShell)

Backend:

```powershell
Set-Location "C:\Users\l0ka\Desktop\2026projects\document_intelligence"
.\legal_env\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m compileall backend
```

Frontend:

```powershell
Set-Location "C:\Users\l0ka\Desktop\2026projects\document_intelligence\frontend"
npm install
npm run dev
```

## Roadmap (near)

- “download all acts (ZIP) if there is a correct way to get files from API links
- Vector Index (HSW/FAISS) for scaling embeddings
- OpenTelemetry/Prometheus-metrics for SLA and API limits

## Private configuration

Provider keys, tokens, passwords, proxy and personal parameters are set through variable environments. `.env.example` contains names without values. `.env` filled and local settings deleted from Git. Do not transmit secrets by command arguments and do not publish real magazines, downloads, certificates or user documents.

To run, export the required variables to the process environment or fill the ignored local `.env` if the entrypoint used is downloading it. The content of `.env` does not in itself become an environment of arbitrary Python command. For Docker Compose, the values of `.env` are transferred to customized services.

JSON/YAML- facilities use `${NAME}` links; configuration loaders allow them through the environment. For numerical values, ${NAME:int}`. Lack of mandatory value causes an error with the name of the variable, without its content. Safe `*.example.json` / `*.example.yaml` save configuration structure.

The names of the private parameters are given in [.env.example](../.env.example). Old values are only retained in the protected local storage facility of the owner; it is not part of the published project. Once the keys are rotated, use new values.

Checking the source and configuration formats does not replace the launch of the infrastructure and model evaluation. Privacy changes do not confirm the quality of AI, the performance of external APIs, or the willingness of the entire system to operate.
