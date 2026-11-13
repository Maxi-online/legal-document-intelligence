from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import httpx
from service import PravoTechService
from fastapi.responses import Response

app = FastAPI(title="Casebook API Service", version="1.0.0")

pravo_service = PravoTechService()  # Сервис для работы с Casebook API 3.0

class SearchRequest(BaseModel):
    query: str
    search_type: str  # "fio", "inn", "company"

class SearchResponse(BaseModel):
    results: List[dict]
    total: int

@app.get("/api/acts/{act_id}/download")
async def download_act(act_id: str):
    """
    Скачивание файла акта через Casebook API 3.0.
    В production версии должен быть реализован реальный запрос к API для получения документа.
    """
    # TODO: Реализовать реальный запрос к Casebook API 3.0 для скачивания документа
    raise HTTPException(
        status_code=501,
        detail="Скачивание файлов актов через Casebook API 3.0 еще не реализовано"
    )

@app.post("/api/search")
async def search(request: SearchRequest):
    """
    Поиск судебных актов через Casebook API 3.0.
    Требует наличия учетных данных (username/password или api_key) в settings.json.
    """
    try:
        print(f"[API_SEARCH] Запрос поиска: query={request.query}, search_type={request.search_type}")
        # Используем реальный API Casebook 3.0
        results = await pravo_service.search_cases(
            query=request.query,
            search_type=request.search_type
        )
        
        print(f"[API_SEARCH] Получено результатов: {len(results)}")
        if results:
            first_result = results[0]
            print(f"[API_SEARCH] Первый результат: case_number={first_result.get('case_number')}, act_text присутствует={bool(first_result.get('act_text'))}, act_text длина={len(first_result.get('act_text', '')) if first_result.get('act_text') else 0}")
        
        return {
            "results": results,
            "total": len(results)
        }
    except HTTPException:
        # Пробрасываем HTTPException как есть (уже содержит правильный статус и детали)
        raise
    except Exception as e:
        # Обрабатываем все остальные ошибки
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка при поиске через Casebook API 3.0: {str(e)}"
        )

class EnrichRequest(BaseModel):
    case_id: str
    document_id: str

@app.post("/api/enrich")
async def enrich_document(request: EnrichRequest):
    """Загрузка полного текста документа для обогащения результатов из кэша"""
    try:
        # Используем внутренний метод _enrich_with_document_texts через временный список
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
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "pravo_tech_casebook_api_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
