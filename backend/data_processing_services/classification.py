from celery import Celery
from openai import AsyncOpenAI
import json
import sys
import logging
from pathlib import Path

# Add a path to backend for the import of utils
backend_path = str(Path(__file__).parent.parent.parent)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
from utils import get_openai_api_key
from utils import apply_openai_proxy_env

app = Celery('classification')
app.config_from_object('celeryconfig')

# We're setting the logic for Celery -- we're using the root logger that Celery has already set up
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

_client = None

def _get_client():
    global _client
    if _client is None:
        apply_openai_proxy_env()
        _client = AsyncOpenAI(api_key=get_openai_api_key())
    return _client

@app.task
def classify_mention(case_number: str, act_text: str, query: str) -> dict:
    """
    Classification of the role of the person in the case
    
    Args:
        case_number: Case number
        act_text: Text of the judicial act
        query: Search request (FIO/INN/name)
    
    Returns:
        Vocabulary with Classification of Role
    """
    try:
        system_prompt = 'You\'re an expert in the classification of participants in trials. Your job is to determine exactly the role of individuals in court cases.\n\nDetermine the type of reference to the person/organization in the court case. Possible types according to TK:\n- ""participant" - person is a party to the case (claimer, defendant, third person, creditor, debtor))\n- "the person mentioned" - the person is mentioned in the text of the act but is not a party to the case\n- "counterparty" - person is a party to the contract or transaction referred to in the case\n- "Affiliated person" - person connected to a party (founder, manager, company related)\n\nClassification rules:\n1. If the person is a party to the case (party, third party), return the "participant""\n2. If a person is mentioned in the text but is not a party, return the "named person""\n3. If a person is referred to as a party to a contract/transaction, return the "contractor""\n4. If the person is connected to the participant (founder, director, etc.), return the "affiliated person""\n\nYou have to return the result in the JSON format. JSON Structure:\n{\n    "classification": "name_Type",\n    "confidence": number_from_0_up to_1,\n    "reasoning": "Brief rationale for classification"\n}\n\nIf reference is not found in the text, return:\n{\n    "classification": "not found",\n    "confidence": 0.0,\n    "reasoning": "No reference found in the text"\n}'

        user_prompt = f"""Text of the judicial act:
{act_text}

Classify the role: {query}"""

        import asyncio
        
        async def get_response():
            logger.info(f"[CLASSIFICATION] Request OpenAI for case {case_number}, query={query}")
            logger.info(f"The length of act_text: {len(act_text) if act_text else 0}")
            if act_text:
                logger.info(f"First 500 act_text characters: {act_text[:500]}")
            else:
                logger.warning(f"[CLASSIFICATION] act_text WAY FOR THE PROCESS {case_number}!")
            
            response = await _get_client().chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            response_text = response.choices[0].message.content
            logger.info(f"[CLASSIFICATION] Response from OpenAI (first 500 characters): {response_text[:500] if response_text else 'EMPTY'}")
            return response_text
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        response_text = loop.run_until_complete(get_response())
        
        if not response_text:
            return {
                "classification": "не определено",
                "confidence": 0.0,
                "reasoning": 'An empty answer from LLM'
            }
        
        # GPT-5 with response_format={"type": "json_object"} returns pure JSON
        # But just in case we're cleaning up possible markdown blocks
        cleaned_text = response_text.strip()
        
        # Take out the Markdown code blocks if there is (in case the model did return it))
        if "```" in cleaned_text:
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned_text, re.DOTALL)
            if json_match:
                cleaned_text = json_match.group(1)
            else:
                parts = cleaned_text.split("```")
                if len(parts) >= 3:
                    cleaned_text = parts[1].strip()
                    if cleaned_text.startswith("json"):
                        cleaned_text = cleaned_text[4:].strip()
        
        # Trying to find JSON object in the text (in case there's an extra text))
        json_start = cleaned_text.find("{")
        json_end = cleaned_text.rfind("}")
        if json_start != -1 and json_end != -1 and json_end > json_start:
            cleaned_text = cleaned_text[json_start:json_end+1]
        
        try:
            result = json.loads(cleaned_text)
            logger.info(f"[CLASSIFICATION] Successfully unsold by JSON for a case {case_number}: {result}")
            
            # Check that the classification is valid.
            classification = result.get("classification", "")
            if not classification or classification == "не найдено":
                # Check if there's really a query in the text.
                if query.lower() in act_text.lower() if act_text else False:
                    # Query's in the text, but LLM didn't find-- use fallsback
                    logger.warning(f"LLM did not find a classification for the case {case_number}, But query is in the text. We're gonna use a fallback.")
                    result["classification"] = "упомянутое лицо"
                    result["confidence"] = 0.5
                    result["reasoning"] = 'Reference found in the text, but LLM did not define the role'
            
            return result
        except json.JSONDecodeError as e:
            # We are trying to extract classification from the text according to TZ
            response_lower = response_text.lower() if response_text else ""
            classification = "упомянутое лицо"  # By default, if not a participant
            
            # Checking for priority according to TK
            if any(word in response_lower for word in ["участник", 'party', "истец", "ответчик", "третье лицо", "кредитор", "должник"]):
                classification = "участник"
            elif "контрагент" in response_lower or "договор" in response_lower or "сделка" in response_lower:
                classification = "контрагент"
            elif any(word in response_lower for word in ['Affiliated', 'Founder', 'Head', 'Affiliated']):
                classification = "аффилированное лицо"
            elif "упомянут" in response_lower or "упоминается" in response_lower:
                classification = "упомянутое лицо"
            
            return {
                "classification": classification,
                "confidence": 0.6,
                "reasoning": response_text[:200] if response_text else 'Classification implemented'
            }
            
    except Exception as e:
        logger.error(f"[Classification: Error to the business {case_number}: {e}", exc_info=True)
        return {
            "classification": "не определено",
            "confidence": 0.0,
            "reasoning": f"Error in classification: {str(e)}"
        }
