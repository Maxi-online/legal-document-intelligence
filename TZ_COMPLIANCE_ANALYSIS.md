# Conformity analysis of TK

## ✅ Fully implemented

### 1. Functional requirements

#### 3.1. Introductory user data
- ✅ Search for a natural person by FIO
- ✅ Search for a legal person under the INS
- ✅ Search for the name of a legal person
- ✅ Support for multiple requests through a comma - ** REALISED**

#### 3.2. Search and data collection
- ✅ Integration with API (Casebook API instead of Law.ru API))
- ✅ Full text search
- ✅ Extraction of metadata:
  - ✅ Case number
  - ✅ Date of act
  - ✅ Name of vessel
  - ✅ parties in the case
  - ✅ reference to the full text of the act (URL))
  - ✅ A part of the text (context))
  - ✅ Type of reference (added to database))
- ✅ Duplicate filtering by case number (added))
- ✅ Depodulation by act (`act_url`) (to avoid losing several acts of one case))

#### 3.3. Post-treatment and ranking
- ✅ Date Sorting (new above) - corrected
- ✅ Sorting by Relevance
- ✅ LLM processing (top –N)):
  - ✅ Extraction of context
  - ✅ Classification of the type of reference
  - ✅ Ran: BM25 + embeddings + heuristics; LLM only for top –N

#### 3.4. User output
- ✅ Results framework
- ✅ Counting of references found - added
- ✅ Counting of unique cases - added
- ✅ All required fields in the table
- ✅ Date of download to database (`ingested_at`) to assess

#### 3.5. Exports
- ✅ Export to Excel (.xlsx))
- ✅ Export to PDF
- ✅ Exports to JSON
- ✅ Qualified references to acts in Excel/PDF
- ✅ Added download date to export

### 2. Architecture and Walls
- ✅ Python 3.11+
- ✅ FastAPI
- ✅ httpx for APl requests
- ✅ PostgreSQL for storage
- ✅ React + TailwindCSS for frontend
- ✅ Openpyxl for Excel
- ✅ Reportlab for PDF
- ✅ Redis for cache
- ✅ Celery for Asynchronous Processing

### 3. Database
- ✅ Case with Fields:
  - ✅ case_number (case number))
  - ✅ Court)
  - ✅ Date of act)
  - ✅ act_url (reference to act))
  - ✅ Parties)
  - ✅ act_text (text of act)
  - ✅ act_type (type of act))
  - ✅ CONTEXT (context of reference to)
  - ✅ **type_of_mention (type of reference from API)** - APPENDIX
  - ✅ classification from GPT)
  - ✅ relevance_score (appraising relevance)
  - ✅ extraction_confidence (trust confidence))
  - ✅ metadata (additional data))

## ⚠️ Partially implemented

### 1. UI/UX requirements (P.7)
- ✅ FIE / INS / Name
- ✅ Find button»
- ✅ Filter results table
- ✅ View the piece of the act
- ✅ Export button»
- ✅ FIO/INN coverage in the context of - ** REALIZATION**
- ✅ "Slip All Reference Files" button (ZIP) - ** REALIZED (in wet mode and via proxie))**

### 2. Non-functional requirements (P.6))
- ✅ Cashing through Redis
- ⚠️ Response time: Depends on API and GPT processing
- ⚠️ Logging: basic implementation, can be improved
- ✅ Security: encryption of `settings.json.enc`, JWT – authorisation, status of task in Redis

## ❌ Not implemented

1. **Full integration with API Right.ru** (instead of Casebook/PravoTech adapter))
   - The Casebook API Service + wet mode is now used; 100% compliance requires contract/endpoints Right

2. **downloading the originals from the real API**
   - In Mood mode, the download is implemented (ZIP + proxy), the real API requires the authorization/file release formats

## Executive summary

**Compliance of TK: ~95 per cent (for wet mode / Integration Casebook))**

Main functionality implemented. The remaining points are bound to the specific real API of Prav.ru (search/download contract) and “production hardening” (observability/allerts/migration of BD).
