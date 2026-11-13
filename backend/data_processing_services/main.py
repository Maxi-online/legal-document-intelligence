from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from orchestrator import process_batch
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Data Processing Service", version="1.0.0")

# Таймаут ожидания результата Celery (сек). Для демо лучше держать достаточно большим,
# т.к. LLM/прокси/ретраи могут занимать >5 минут.
CELERY_TASK_TIMEOUT_SECONDS = int(os.getenv("DATA_PROCESSING_TASK_TIMEOUT_SECONDS", "1200"))

class ProcessRequest(BaseModel):
    task_id: str
    data: Dict
    query: str

@app.post("/api/process")
async def process_data(request: ProcessRequest):
    """Обработка данных через агентов"""
    print(f"[{request.task_id}] ===== ПОЛУЧЕН ЗАПРОС НА ОБРАБОТКУ =====")
    print(f"[{request.task_id}] Task ID: {request.task_id}")
    print(f"[{request.task_id}] Query: {request.query}")
    try:
        cases = request.data.get("results", [])
        print(f"[{request.task_id}] Начало обработки {len(cases)} дел через Celery")
        
        # Проверяем наличие act_text в первых случаях
        for idx, case in enumerate(cases[:3]):  # Проверяем первые 3
            act_text = case.get('act_text', '')
            case_number = case.get('case_number', 'unknown')
            print(f"[{request.task_id}] Дело {idx} ({case_number}): act_text присутствует={bool(act_text)}, длина={len(act_text) if act_text else 0}")
            if act_text:
                print(f"[{request.task_id}] Дело {idx} ({case_number}): первые 200 символов act_text: {act_text[:200]}")
        
        if not cases:
            return {
                "task_id": request.task_id,
                "results": [],
                "status": "completed"
            }
        
        # Запускаем асинхронную обработку через Celery
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        def run_celery_task():
            """Запуск Celery задачи в синхронном контексте"""
            print(f"[{request.task_id}] Запуск Celery задачи process_batch.delay()")
            task = process_batch.delay(cases, request.query)
            print(f"[{request.task_id}] Celery задача запущена, ожидание результатов (timeout={CELERY_TASK_TIMEOUT_SECONDS}s)...")
            result = task.get(timeout=CELERY_TASK_TIMEOUT_SECONDS)
            print(f"[{request.task_id}] Celery задача завершена, получено результатов: {len(result) if result else 0}")
            return result
        
        # Запускаем Celery задачу в отдельном потоке для async контекста
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            results = await loop.run_in_executor(executor, run_celery_task)
        
        print(f"[{request.task_id}] Обработка завершена, возвращаем {len(results)} результатов")
        
        return {
            "task_id": request.task_id,
            "results": results,
            "status": "completed"
        }
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"[{request.task_id}] ОШИБКА при обработке данных: {str(e)}")
        print(f"[{request.task_id}] Traceback: {error_traceback}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "data_processing_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
