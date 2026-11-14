from celery import Celery
from openai import AsyncOpenAI
import json
import re
import sys
from pathlib import Path

# Add a path to backend for the import of utils
backend_path = str(Path(__file__).parent.parent.parent)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
from utils import get_openai_api_key
from utils import apply_openai_proxy_env

app = Celery('ranking')
app.config_from_object('celeryconfig')

_client = None

def _get_client():
    global _client
    if _client is None:
        apply_openai_proxy_env()
        _client = AsyncOpenAI(api_key=get_openai_api_key())
    return _client

@app.task
def rank_relevance(case_number: str, act_text: str, query: str) -> dict:
    """
    Rating the relevance of the reference
    
    Args:
        case_number: Case number
        act_text: Text of the judicial act
        query: Search request (FIO/INN/name)
    
    Returns:
        A dictionary assessing relevance
    """
    try:
        # Compute the frequency of references
        mentions_count = len(re.findall(re.escape(query), act_text, re.IGNORECASE))
        
        prompt = f"""Assess the relevance of the reference to \"{query}And in the next court act.

Text of the judicial act:
{act_text}

Number of references \"{query}": {mentions_count}

Assess relevance by the following criteria:
1. Frequency of references (more references = above relevance)
2. The importance of the role in the case (the plaintiff/defendant is more important than the witness))
3. Key points of reference (participation in decisions, existence of obligations, etc.).)
4. Relevance of reference for search request

Return the result to JSON:
{{
    \"relevance_score\": number_from_0_up to_1,
    \"factors\": {{
        \"mention_frequency\": number,
        \"role_importance\": number_from_0_up to_1,
        \"context_importance\": number_from_0_up to_1,
        \"overall_relevance\": number_from_0_up to_1
    }},
    \"explanation\": \"Summary explanation of the valuation\"
}}

If \"{query}\"not found in the text, give it back:
{{
    "relevance_score": 0.0,
    "factors": {{
        "mention_frequency": 0,
        "role_importance": 0.0,
        "context_importance": 0.0,
        "overall_relevance": 0.0
    }},
    \"explanation\": \"No reference found\"
}}
"""

        import asyncio
        
        async def get_response():
            response = await _get_client().chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": "You're an expert on the relevance of documents. Your job is to accurately assess the importance of mentioning in court acts."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        response_text = loop.run_until_complete(get_response())
        
        try:
            result = json.loads(response_text)
            return result
        except json.JSONDecodeError:
            # Compute a baseline estimate based on frequency of references
            base_score = min(mentions_count / 10, 1.0) if mentions_count > 0 else 0.0
            
            return {
                "relevance_score": base_score,
                "factors": {
                    "mention_frequency": mentions_count,
                    "role_importance": 0.5,
                    "context_importance": 0.5,
                    "overall_relevance": base_score
                },
                "explanation": f"The evaluation is based on the frequency of references: {mentions_count}"
            }
            
    except Exception as e:
        print(f"Error in ranking: {e}")
        # Baseline evaluation based on frequency of references
        mentions_count = len(re.findall(re.escape(query), act_text, re.IGNORECASE)) if act_text else 0
        base_score = min(mentions_count / 10, 1.0) if mentions_count > 0 else 0.0
        
        return {
            "relevance_score": base_score,
            "factors": {
                "mention_frequency": mentions_count,
                "role_importance": 0.5,
                "context_importance": 0.5,
                "overall_relevance": base_score
            },
            "explanation": f"Error in ranking: {str(e)}"
        }
