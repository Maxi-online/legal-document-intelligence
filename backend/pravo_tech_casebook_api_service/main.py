from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import httpx
from service import PravoTechService
from fastapi.responses import Response

app = FastAPI(title="Casebook API Service", version="1.0.0")

pravo_service = PravoTechService()  # Service for Casebook API 3.0

class SearchRequest(BaseModel):
    query: str
    search_type: str  # "fio", "inn", "company"

class SearchResponse(BaseModel):
    results: List[dict]
    total: int

@app.get("/api/acts/{act_id}/download")
async def download_act(act_id: str):
    """
    downloading the act file through the Casebook API 3.0.
    In the production version, a real request for an API to receive a document must be implemented.
    """
    # TODO: Implement a real request for the Casebook API 3.0 for downloading document
    raise HTTPException(
        status_code=501,
        detail='The downloading of act files through the Casebook API 3.0 has not yet been implemented'
    )

@app.post("/api/search")
async def search(request: SearchRequest):
    """
    Searching for court acts through Casebook API 3.0.
    Requires accounting data (username/password or api_key) in settings.json.
    """
    try:
        print(f"[API_SEARCH] Search request: query={request.query}, search_type={request.search_type}")
        # Use real API Casebook 3.0
        results = await pravo_service.search_cases(
            query=request.query,
            search_type=request.search_type
        )
        
        print(f"[API_SEARCH] Results obtained: {len(results)}")
        if results:
            first_result = results[0]
            print(f"[API_SEARCH] First result: case_number={first_result.get('case_number')}, act_text present={bool(first_result.get('act_text'))}, act_text length={len(first_result.get('act_text', '')) if first_result.get('act_text') else 0}")
        
        return {
            "results": results,
            "total": len(results)
        }
    except HTTPException:
        # Throw HTTPException as it is (already contains the correct status and details))
        raise
    except Exception as e:
        # Processing all other errors
        raise HTTPException(
            status_code=500,
            detail=f"Internal error when searching through Casebook API 3.0: {str(e)}"
        )

class EnrichRequest(BaseModel):
    case_id: str
    document_id: str

@app.post("/api/enrich")
async def enrich_document(request: EnrichRequest):
    'Loading the full text of the document to enrich the cache results'
    try:
        # Use the internal method _enrich_with_document_texts through the interim list
        temp_results = [{
            "metadata": {
                "case_id": request.case_id,
                "document_id": request.document_id
            }
        }]
        await pravo_service._enrich_with_document_texts(temp_results)
        act_text = temp_results[0].get("act_text", "") if temp_results else ""
        return {"act_text": act_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading document text: {str(e)}")

@app.get("/health")
async def health():
    'Service health check'
    return {"status": "healthy", "service": "pravo_tech_casebook_api_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
