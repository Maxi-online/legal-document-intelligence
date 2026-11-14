from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from orchestrator import process_batch
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Data Processing Service", version="1.0.0")

# Celery timeout). For a demo, it's better to keep it big enough,
# t.s. LLM/proxi/retrai may take > 5 minutes.
CELERY_TASK_TIMEOUT_SECONDS = int(os.getenv("DATA_PROCESSING_TASK_TIMEOUT_SECONDS", "1200"))

class ProcessRequest(BaseModel):
    task_id: str
    data: Dict
    query: str

@app.post("/api/process")
async def process_data(request: ProcessRequest):
    'Data processing through agents'
    print(f"[{request.task_id}== sync, corrected by elderman == @elder_man")
    print(f"[{request.task_id}] Task ID: {request.task_id}")
    print(f"[{request.task_id}] Query: {request.query}")
    try:
        cases = request.data.get("results", [])
        print(f"[{request.task_id}] Start of processing {len(cases)} Celery")
        
        # Check for act_text in first cases
        for idx, case in enumerate(cases[:3]):  # Checking the first three.
            act_text = case.get('act_text', '')
            case_number = case.get('case_number', 'unknown')
            print(f"[{request.task_id}] Case {idx} ({case_number}): act_text present={bool(act_text)}, length={len(act_text) if act_text else 0}")
            if act_text:
                print(f"[{request.task_id}] Case {idx} ({case_number}): the first 200 act_text characters: {act_text[:200]}")
        
        if not cases:
            return {
                "task_id": request.task_id,
                "results": [],
                "status": "completed"
            }
        
        # Start asynchronous processing via Celery
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        def run_celery_task():
            'Launching Celery Tasks in Simultaneous Context'
            print(f"[{request.task_id}] Launch Celeery task process_batch.delay()")
            task = process_batch.delay(cases, request.query)
            print(f"[{request.task_id}] Celery task started, waiting for results (timeout={CELERY_TASK_TIMEOUT_SECONDS}s)...")
            result = task.get(timeout=CELERY_TASK_TIMEOUT_SECONDS)
            print(f"[{request.task_id}] Celery mission completed, results obtained: {len(result) if result else 0}")
            return result
        
        # Start a Celery task in a separate stream for an async context
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            results = await loop.run_in_executor(executor, run_celery_task)
        
        print(f"[{request.task_id}] Processing completed, returned {len(results)} Results")
        
        return {
            "task_id": request.task_id,
            "results": results,
            "status": "completed"
        }
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"[{request.task_id}] Error in the processing of data: {str(e)}")
        print(f"[{request.task_id}] Traceback: {error_traceback}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    'Service health check'
    return {"status": "healthy", "service": "data_processing_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
