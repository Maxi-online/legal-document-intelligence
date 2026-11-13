"""Inspect the real mock-source contract; no legal search or LLM calls are made."""
import json,random
from datetime import datetime
from backend.pravo_tech_casebook_api_service.mock_data import generate_mock_casebook_response

def run(): return {"mode":"synthetic-casebook-source","response":generate_mock_casebook_response("Demo Person",count=3,rng=random.Random(7),reference_time=datetime(2026,1,1)),"live_source_verified":False}
if __name__=="__main__": print(json.dumps(run(),ensure_ascii=False,indent=2,default=str))
