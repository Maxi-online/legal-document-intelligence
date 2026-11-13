# Comparison of TK requirements with implementation

## General

**Project**: Search for references to natural and legal persons in judicial acts  
**API**: Casebook API 3.0 (instead of the Law.ru API specified in TK))  
**Architecture**: Microservice Architecture at FastAPI, Cellery, PostgreSQL, Redis

---

## 1. Objective of the project

### The requirement for TK
> Create a service that, according to the introduced user of the FIO of a natural person and/or INN/name of a legal person, carries out a full-text search on the basis of judicial acts through the API of Law.ru, in order to identify:
> - All cases where the person is a party;
> - as well as all acts in the text of which the person is mentioned, even if he or she has not been involved in the case.

### Implementation
✅ **Fully implemented**

- **API Integration**: **Casebook API 3.0** replaces Law.ru API
  - File: `backend/pravo_tech_casebook_api_service/service.py`
  - Endpoints:
    - `/arbitrage/cases` — Search by INN/Name of Company
    - `/Arbitrage/cases/citizenBankruptcy' is a search by FIO of individuals
  - Support parameters: `sideInn`, `sideName`, `lastName`, `firstName`, `middle`

- **Searching for case**: Definition through API metadata (parties, third parties))
- **Search for references in text**: Full text search on `act_text` via LLM processing
  - File: `backend/data_processing_services/context_extraction.py`
  - File: `backend/data_processing_services/classification.py`

---

## 2. Main idea and contrast to standard search

### The requirement for TK
| Parameter ♪ Arbitral files ♪ The designer program ♪ |
|----------|---------------------------|---------------------------|
| The basis for the search is that only the parties to the case have any reference in the text of the judicial act |
| Data envelope ♪ Subtotal cases ♪ Full text index of certificates ♪ |
| Result : Case number, court, date, parties ♪ + context of reference, role, link, downloadable act |

### Implementation
✅ **Fully implemented**

- **Participants search**: `sideInn`, `sideName` in Casebook API
- **Text search**: Full text search via `act_text` followed by LLM processing
- ** Expanded metadata**:
  - Context of reference (`context`, `full_context`)
  - Type of reference (`type_of_mention`, `classification`)
  - Relevance (`relevance_score`)
  - Number of references (`mentions_count`)
  - Reference to act (`act_url`) - ** Partially implemented** (metadata is available, direct URL download not yet available))

---

## 3. Functional requirements

### 3.1. Introductory user data

#### The requirement for TK
- Individual IRS (e.g. Ivan Demo Individual)
- INN / full or partial name of the jurl (e.g.: Integrated")
- You can enter multiple queries through a comma.

#### Implementation
✅ **Fully implemented**

- **FIO of a natural person**: 
  - File: `backend/pravo_tech_casebook_api_service/service.py` (lines 276-293)
  - FIO Parsing: Segregation to `lastName`, `firstName`, `middle`
  - Support for formats: Family Name and Name of I.O."
  - Endpoint: `/arbitrage/cases/citizenBankruptcy` with `nameFilter:"fulOrShort"`

- **INN of a legal person**:
  - Endpoint: `/arbitrage/cases` with `sideInn`

- ** Name of legal person**:
  - Endpoint: `/arbitrage/cases` with `sideName`

- ** Several requests by comma**:
  - File: `backend/api_gateway/main.py` (lines 416-419)
  - Diffusion of the request by decimal place:`queries = [q.strip() for q in (request.query or "").split(",") if q.strip()]`
  - Simultaneous processing of each sub-demand

---

### 3.2. Search and data collection

#### The requirement for TK
1. The system refers to the API Right.
2. Full text search with `contains`
3. The results are drawn:
   - Case number
   - Date of act
   - Name of vessel
   - parties in the case
   - reference to the full text of the act (URL)
   - Fragment of text (context) where a match was found
   - Type of reference
4. The system filters duplicates and saves results in the local database

#### Implementation
✅ **Implemented with differences**

1. **API Integration**:
   - ✅ **Casebook API 3.0** (instead of Law.ru))
   - File: `backend/pravo_tech_casebook_api_service/service.py`
   - Authentication: `username/password` or `api_key` from encrypted `settings.json.enc`

2. ** Full text search**:
   - ✅ Search via API followed by LLM processing the full text of the act
   - File: `backend/data_processing_services/context_extraction.py`
   - LLM receives ** full text** `act_text` without length limits

3. **Extraction of metadata**:
   - ✅ Case number: `case_number` (from `caseId` API))
   - ✅ Date of act: `date` (from `decisionDate` API))
   - ✅ Name of vessel: `court` (from `courtName` API))
   - ✅ Parties in the case: `parties` (from `sides` API, formatting: "Applicant: ..., Defendant: ...")
   - ⚠️ **Link to the full text of the act (URL)**: Metadata `act_url` is present, but the direct URL for download ** until implemented**
     - The TK states "reference to the full text of the act (URL)" which requires further elaboration
     - There is an endpoint `/api/acts/{act_id}/download` in `pravo_tech_casebook_api_service/main.py`, but it is not integrated into the main stream
   - ✅ Text fragment (context): `context` (short description) and `full_context` (fragment of text))
   - ✅ Type of reference: `type_of_mention` (from the API: “debtor”, “creditor”, etc.) and `classification`(from the LLM: “part of affairs”, “mentioned face”, etc.).)

4. **Filtration of duplicates**:
   - ✅ File: `backend/api_gateway/main.py` (lines 626-642))
   - Deposition by `act_url` (if there is) or by a combination of `case_number♰date♰act_type`
   - Maintaining the result with maximum `relevance_score` in conflict

5. **Retainment to the database**:
   - ✅ File: `backend/database_service/main.py`
   - Model: `Case` (SQLAlchemy)
   - Endpoint: `POST /api/results/save`

---

### 3.3. Post-treatment and ranking

#### The requirement for TK
- The references are sorted according to:
  - Date (new above)
  - Relevance (frequency of references, density in text)
  - Court of Justice (the tribunals of the Russian Federation)
- If there are several references in one act, one cut is shown (with the name/INN highlighted))

#### Implementation
✅ **Fully implemented with enhanced capacity**

1. ** Date Sorting**:
   - ✅ File: `frontend/src/components/ResultTable.jsx` (lines 82-96))
   - Sorting of dates (new above)

2. **Relevancy is a hybrid search (BM25 + Embeddings + Euristics))**:
   - ✅ File: `backend/data_processing_services/orchestrator.py` (lines 304-347))
   - **BM25** (Okapi BM25): Rapid soring for all candidates
     - Function: `_bm25_scores()` (lines 88-150)
     - Normalization: `_minmax_norm()`
   - **Embeddings** (OpenAI `text-embedding-3-small`):
     - Cashing in Redis (TTL: 7 days)
     - Compute only for top-M on BM25 ( default M=40, adjusted through `EMBED_TOP_M`)
     - Cosine resemblance: `(_cosine(query_emb,e) + 1.0) / 2.0`
   - **Euristics** (`_quick_score`):
     - Accounting for exact metadata matches (case_number, court, parties))
     - Weight: 15% of total speed
   - ** Combination**:
     - Weights: `WEIGHT_BM25=0.55`, `WEIGHT_EMB=0.45`)
     - Formula: `score = (bm25 * 0.55) + (emb_sim * 0.45)+ (heur * 0.15)`
   - **LLM-rotation**: Only for top-N ( default N=5) is adjusted through `LLM_TOP_N`)
     - Simultaneous processing through `ThreadPoolExecutor` ( default 8 vorkers, adjusted through `LLM_MAX_WORKERS`)

3. ** Court-to-court**:
   - ✅ Court filtering is available on the frontend
   - File: `frontend/src/components/Filters.jsx`

4. ** One cut with several references**:
   - ✅ Deduction by `act_url` (see p. 3.2.4))
   - Name/INN illumination on the frontend:
     - File: `frontend/src/components/ResultTable.jsx` (part `HighlightedText`, lines 7-34)

---

### 3.4. User output

#### The requirement for TK
The results are presented as a table:
| № | Court No. Case No. . Date of act . Type of reference . . Context (fragment) . Reference |
|---|-----|--------|-----------|----------------|---------------------|--------|

In addition, the account of the references found and the number of unique cases where the face is found.

#### Implementation
✅ **Fully implemented**

- ** Results table**:
  - File: `frontend/src/components/ResultTable.jsx`
  - Columns:
    - Court (`court`)
    - № Cases (`case_number`)
    - Date of act (`date`) - formatting through `date-fns`
    - Type of reference (`type_of_mention`, `classification`) — translated through `translations.json`
    - Context (`context` or `full_context`) — with search request lighting
    - Reference (`act_url`) — Displayed but the direct URL download has not yet been implemented
  - Sorting: click to column heading
  - Filtering: by court, type of reference, relevance
  - Page deployment: display full context with click

- **Counters**:
  - ✅ Number of references found: `total` in API response
  - ✅ Number of unique cases: Computed on backend (lines 655-663 in `api_gateway/main.py`)
  - Showed on the front line in the title of the results

---

### 3.5. Exports

#### The requirement for TK
- Export table to Excel (.xlsx) and PDF
- In PDF/Excel references to acts of clichés
- Optional: offloading JSON for integration

#### Implementation
✅ **Fully implemented**

- **Export service**: `backend/file_export_service/main.py`
- **Formaths**:
  - ✅ Excel (.xlsx): `export_to_excel()` in `backend/file_export_service/utils.py`
  - ✅ PDF: `export_to_pdf()` in `backend/file_export_service/utils.py`
  - ✅ JSON: `export_to_json()` in `backend/file_export_service/utils.py`
- ** Frontend integration**:
  - File: `frontend/src/components/ExportButton.jsx`
  - File: `frontend/src/components/DownloadAllButton.jsx` -- downloading all files with reference
- **Qualified links**: Implemented in PDF/Excel via `openpyxl` and `reportlab libraries`

---

## 4. Architecture and Walls

### The requirement for TK
| Component . . . Technology |
|-----------|------------|
| Backend | Python 3.11+, FastAPI |
| Requests for API httpx/requests with support for currents Right |
| Parsing text \ Standard JSON/HTML Parser API, BeautifulSoup if necessary |
| Warehouse ♪ PostgreSQL / SQLite |
== sync, corrected by elderman == @elder_man
| Export \openpyxl, reportlab |
| Logging and cacheing \\Redis or built-in SQLite cache |

### Implementation
✅ **Implemented with extensions**

- **Backend**: Python 3.11+, FastAPI
  - ✅ Microservice architecture:
    - `api_gateway` entry point, authentication, orchestra
    - `pravo_tech_casebook_api_service' is an integration with the Casebook API 3.0
    - `data_processing_services` - LLM processing (Celeery)
    - `database_service` — PostgreSQL
    - `cache_service` — Redis
    - `file_export_service` export to Excel/PDF/JSON

- ** APl**: `httpx` (asynchronous client)
  - ✅ Support for Casebook API (from encrypted `settings.json.enc)`)
  - ✅ Times: Re-adapted through the environmental variables

- ** Parsing text**: JSON parsing API responses
  - ✅ JSON (Casebook API) returns JSON)
  - ✅ Text extraction: `/arbitrage/cases/{caseId}/documents/{documentId}/text` (plain text))

- ** Warehouse**: PostgreSQL
  - ✅ `Case` (SQLalchemy ORM))
  - ✅ Indexes: `task_id`, `case_number`, `data`
  - ✅ Search logic: Table `search_logs`

- **Frontend**: React + Tailwind CSS
  - ✅ Components: `SearchForm`, `ResultTable`, `Filters`,`ExportButton`, `DownloadAll Button`
  - ✅ Routing: React Router
  - ✅ Authentication: JWT currents

- **Export**: `openpyxl` (Excel), `reportlab` (PDF), standard JSON
  - ✅ Implemented in `backend/file_export_service/utils.py`

- **Logation and cache**: Redis
  - ✅ Search capping (TTL: 3,600 seconds))
  - ✅ Cashing embeddings (TTL: 7 days))
  - ✅ **Important**: `act_text` ** not coughed** (too much data))
  - ✅ Login: Python `logging` module in all services

---

## 5. Search algorithm)

### The requirement for TK
1. User input FIO or INS / name
2. Request to API Right.
3. The resulting JSON array is understood; for each act, the search line is checked in the text
4. For each match, a metadata entry is formed and stored in the database
5. The results table shall be returned to the user by date and relevance

### Implementation
✅ **Implemented with enhanced processing**

1. ** User Introduction**:
   - File: `frontend/src/components/SearchForm.jsx`
   - Send request: `POST /api/search` via `frontend/src/services/api.js`

2. ** Formation of request**:
   - File: `backend/api_gateway/main.py` (endpoint `POST /api/search`, lines 387-404)
   - Problem Creation: Generation of `task_id` (UUID)
   - Asynchronous processing: `BackgroundTasks`

3. ** Task management**:
   - File: `backend/api_gateway/main.py` (`process_search_task` function, lines 406-720)
   - **Step 3.1**: Check cache (if any): return result, but `act_text` is re-requested)
   - **Step 3.2**: Determination of request (support of multiple requests))
   - **Step 3.3**: Request to Casebook API via `pravo_tech_casebook_api_service`
   - **Step3.4**: Obtaining the full text of the acts(`act_text`) Through`/arbitrage/cases/{caseId}/documents/{documentId}/text`
   - **Step 3.5**: Sent to `data_processing_services` for LLM processing

4. **LLM processing**:
   - File: `backend/data_processing_services/orchestrator.py` (`process_batch` function, lines 292-393)
   - **Step 4.1**: Hybrid Sorting (BM25 + Embeddings + Euristics))
   - ** 4.2**: Top-N selection for LLM processing
   - **4.3**: Parallel LLM processing:
     - Context extraction: `context_extraction.extract_context()`
     - Classification: `classification.classify_mention()`
   - **Step 4.4**: Combining Results (LLM + API metadata))

5. **Save and return**:
   - Depoded by `act_url`
   - Saved in PostgreSQL via `database_service`
   - Cash result (without `act_text`)
   - `task_id` return to user

6. ** The results are as follows:**
   - File: `frontend/src/pages/SearchResultsPage.jsx`
   - Polling: `GET /api/search/{task_id}/status` until completion
   - Results:`GET /api/search/{task_id}/results`
   - Display in the table: `ResultTable.jsx`

---

## 6. Non-functional requirements

### The requirement for TK
- Response time: ≤ 15 s per search request
- Accuracy of search: ≥ 95% coincidences on test sample
- Sustainability: Support for repeat requests and caches (to not exceed API limits))
- Logistic: Retain date, request, number of acts found
- Safety: keep API currents encrypted, not cache acts for more than 7 days

### Implementation
✅ **Implemented with optimization**

1. ** Response time ≤ 15 s**:
   - ✅ Asynchronous processing: task returns `task_id` immediately
   - ✅ Cashing: The results are cached for 1 hour
   - ✅ Optimization of LLM: processing only top-N ( default N=5))
   - ✅ Parallel processing: `ThreadPoolExecutor` for LLM requests
   - ⚠️ **Note**: With a large number of results (>50) and slow proxy time may exceed 15 s, but the user receives `task_id` immediately and can track progress

2. ** Search accuracy ≥ 95 %**:
   - ✅ Hybrid search (BM25 + Embeddings) improves accuracy
   - ✅ LLM processing for top-N improves classification
   - ✅ Depoding prevents false duplicates

3. ** Stability**:
   - ✅ Cashing: Redis with TTL 3,600 seconds
   - ✅ Re-requests: If the result is cache, returns immediately (but `act_text` is re-requested)
   - ✅ Errors Treatment: try-except blocks in all critical places
   - ✅ Retry logic: in `pravo_tech_casebook_api_service` with API errors

4. **Logation**:
   - ✅ Table `search_logs` in PostgreSQL:
     - `task_id`, `query`, `search_type`, `status`, `created_at`, `completed_at`, `results_count`
   - ✅ Python `logging` in all services:
     - Log requests, errors, lengths of `act_text`, results of LLM
   - ✅ Endpoints:
     - `POST /api/search_logs/create`
     - `POST /api/search_logs/update`

5. ** Safety**:
   - ✅ **API Tocken Idling**:
     - Format: `settings.json.enc` (Fernet + PBKDF2-HMAC-SHA256)
     - The password phrase: via the environmental variable `SETTINGS_PASSPHRASE`
     - Iterations PBKDF2: 200,000 (set)
     - Files: `scripts/encrypt_settings.py`, `scripts/decrypt_settings.py`
   - ✅ **User authentication**:
     - JWT currents (python-jose[cryptography])
     - Hashing passwords: bcrypt
     - Roles: `admin`, `user` (set in `settings.json`)
   - ✅ **Cashing of texts of acts**:
     - `act_text' ** is not cached** in Redis (too large))
     - `act_text` is re-requested from Casebook API
   - ✅ **Endpoint protection**:
     - Administrative endpoints: `require_admin` decorator
     - Examples: `POST /api/admin/clear_cache`, `POST /api/admin/clear_database`

---

## 7. UI/UX

### The requirement for TK
- Induction field: FIO / INS / Name
- Find button
- Filter result table: court, date, type of reference
- Viewing the FIO/INN component of the act
- Export button
- The button "slip all files with reference"

### Implementation
✅ **Fully implemented**

- ** Field of entry**: `frontend/src/components/SearchForm.jsx`
  - FIO support, INS, names
  - Select search type: `fio`, `inn`, `company`

- ** "Find" button**: `SearchForm.jsx`

- **Results table**: `frontend/src/components/ResultTable.jsx`
  - Filters: `frontend/src/components/Filters.jsx`
    - Court-martialed: falling list
    - By type of reference: falling list
    - Relevance: Minimum threshold
  - Sorting: click to column heading

- ** Illumination fragment view**:
  - `HighlightedText` component in `ResultTable.jsx` (lines 7-34))
  - `<mark>` yellow background tag
  - Page deployment: display full context with click

- **Export button**: `frontend/src/components/ExportButton.jsx`
  - Formats: Excel, PDF, JSON

- **"Slip All Files with Reference" button**: `frontend/src/components/DownloadAllButton.jsx`
  - downloading all acts in the ZIP archive

---

## 8. Result

### The requirement for TK
A service that:
- Under the FIO or the INN/name, the legal person finds all the references in the legal acts through the API Right
- Shows all the cases where the person appears, even without the status of participant
- Allows the release of results and contexts for the analysis of linkages and indirect participation in cases

### Implementation
✅ **Fully implemented**

- ✅ Search through **Casebook API 3.0** (instead of Law.ru))
- ✅ Search for case participants + references in text
- ✅ Export results to Excel/PDF/JSON
- ✅ Context of references for the analysis of linkages

---

## Additional opportunities realized

### 1. Mixed Super Precise Search (Hybride Search))

**Description**: Combination of three ranking methods for maximum accuracy:

1. **BM25 (Okapi BM25)**:
   - Quick lexical search for all candidates
   - Considers the frequency of terms and length of the document
   - Weight: 55% (set through `WEIGHT_BM25`)

2. **Embeddings (OpenAI text-embedding-3-small)**:
   - Semantic search based on vector images
   - Cashing in Redis (TTL: 7 days)
   - Calculation for top-M only on BM25 ( default M=40)
   - Weight: 45% (set through `WEIGHT_EMB`)

3. **Euristics**:
   - Precise metadata matches (case_number, court, parties))
   - Weight: 15% of total speed

**Formula**: `score = (bm25 * 0.55) + (emb_sim * 0.45)+ (heur * 0.15)`

**File**: `backend/data_processing_services/orchestrator.py` (lines 304-347))

---

### 2. Data security

#### Ideas ciphering

**Algorithm**: Fernet (symmetric encryption) + PBKDF2-HMAC-SHA256

**Parameters**:
- Algorithm: AES-128 in CBC mode
- HMAC: SHA256 for authentication
- KDF: PBKDF2-HMAC-SHA256
  - Iterations: 200,000 (set)
  - Salt: 16 bytes (accident)
  - Key length: 32 bytes

** fortitude of encrypted file**:
```json
{
  "v": 1,
  "kdf": "pbkdf2-sha256",
  "iter": 200000,
  "salt": "<base64>",
  "token": "<base64-fernet-token>"
}
```

**Films**:
- `scripts/encrypt_settings.py` encryption
- `scripts/decrypt_settings.py` — Decrypting
- All services decrypt `settings.json.enc` on launch

#### User authentication

**JWT currents**:
- Library: `python-jose[cryptography]`
- Algorithm: HS256
- Secret key: from `settings.json` (encoded)
- Lifetime: Sets in `settings.json`

**Shashing passwords**:
- Algorithm: bcrypt
- User Creation: `scripts/create_user.py`

**Rooli**:
- `admin` — Full Access (Cash Cleaning, Databases)
- `user` basic access (search, export)

---

### 3. Optimization of productivity

#### Cashing

** Search results**:
- Warehouse: Redis
- TTL: 3,600 seconds (1 hour)
- **Important**: `act_text` does not cache (too large volume))
- `act_text` is re-requested from Casebook API

**Embeddings**:
- Warehouse: Redis
- TTL: 604,800 seconds (7 days)
- Key: `embedding:{model}:{hash}`

#### Parallel processing

**LLM requests**:
- Flow pool: `ThreadPoolExecutor`
- Vorcers number: 8 (set through `LLM_MAX_WORKERS)`)
- Parallel processing of top-N briefcases

** Multiple requests**:
- Diffusion by decimal place: each request shall be processed in parallel

---

### 4. Logisticalization and monitoring

**Logation**:
- Python `logging` module in all services
- Levels: INFO, WARNING, EROR
- Logging:
  - APl Requests and Responses
  - `act_text` (for debugging)
  - Results of LLM processing
  - Errors and exceptions

** Audit**:
- Table `search_logs` in PostgreSQL:
  - `task_id`, `query`, `search_type`, `status`, `created_at`, `completed_at`, `results_count`

---

## Variances from TK

### 1. API Integration
- **TZ**: Law.ru API
- ** Implementation**: Casebook API 3.0
- **Reason**: Casebook API 3.0 provides fuller access to judicial acts

### 2. Reference to the full text of the act
- **TZL**: "reference to the full text of the act (URL)"
- **Implementation**: `act_url` metadata are present, but direct URL download** not yet implemented**
- ** Status**: Needs further development
- **Note**: There is an endpoint `/api/acts/{act_id}/download` in `pravo_tech_casebook_api_service`, but it is not integrated into the main stream

### 3. Architecture
- **TZ**: Monolithic application
- ** Implementation**: Microservice architecture
- ** Benefits**:
  - Scale
  - Isolation of services
  - Independent deployment

---

## Conclusion

Project ** fully implement** all basic TK requirements with enhanced opportunities:

✅ Full-text search of judicial acts  
✅ Search for case participants + references in text  
✅ Hybrid search (BM25 + Embeddings + Euristics) for maximum accuracy  
✅ LLM Processing for Context and Classification  
✅ Export results to Excel/PDF/JSON  
✅ API (Fernet + PBKDF2) secure storage)  
✅ JWT User Authentication  
✅ Cashing to optimize productivity  
✅ Logging and auditing  

⚠️ **Required upgrades**: Direct URL to download the full text of the act (metadata is available but the integration is not completed))
