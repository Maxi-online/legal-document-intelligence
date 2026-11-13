from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Dict
from utils import export_to_excel, export_to_pdf, export_to_json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="File Export Service", version="1.0.0")

class ExportRequest(BaseModel):
    task_id: str
    format: str  # "excel", "pdf", "json"
    data: List[Dict]

@app.post("/api/export")
async def export_data(request: ExportRequest):
    """Экспорт данных в указанном формате"""
    try:
        if request.format == "excel":
            file_content = export_to_excel(request.data, request.task_id)
            return Response(
                content=file_content,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="document_intelligence_results_{request.task_id}.xlsx"'}
            )
        elif request.format == "pdf":
            file_content = export_to_pdf(request.data, request.task_id)
            return Response(
                content=file_content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="document_intelligence_results_{request.task_id}.pdf"'}
            )
        elif request.format == "json":
            file_content = export_to_json(request.data, request.task_id)
            return Response(
                content=file_content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="document_intelligence_results_{request.task_id}.json"'}
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Use: excel, pdf, or json")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "file_export_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
