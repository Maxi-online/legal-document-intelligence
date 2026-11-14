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

app = Celery('context_extraction')
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
def extract_context(case_number: str, act_text: str, query: str) -> dict:
    """
    Extraction of the context of reference from the text of the judicial act
    
    Args:
        case_number: Case number
        act_text: Text of the judicial act
        query: Search request (FIO/INN/name)
    
    Returns:
        Vocabulary with context of mention and confidence
    """
    try:
        system_prompt = 'You\'re an expert in the analysis of legal documents. Your task is to extract the context of the references from the judicial acts.\n\nInstructions:\n1. Find all references to the person/organization in the text of the judicial act\n2. Context drawings of each reference (circulating proposals before and after))\n3. Identify the context in which the person is mentioned (e.g. as a party to the case, as a witness, as a third person, etc.).)\n4. Give key information on the role and participation in the process\n5. Calculate the number of references\n\nYou have to return the result in the JSON format. JSON Structure:\n{\n    "context": "Brief description of the context of the reference",\n    "full_context": "The full context with the surrounding proposals",\n    "mentions_count": number,\n    "confidence": number_from_0_up to_1\n}\n\nIf reference is not found in the text, return:\n{\n    "context": "No reference found",\n    "full_context": "",\n    "mentions_count": 0,\n    "confidence": 0.0\n}'

        user_prompt = f"""Text of the judicial act:
{act_text}

Context of mention: {query}"""

        import asyncio
        
        async def get_response():
            logger.info(f"[CONTEXT_EXTRACTION] Request OpenAI for case {case_number}, query={query}")
            logger.info(f"[CONTEXT_EXTRACTION] Length of act_text: {len(act_text) if act_text else 0}")
            if act_text:
                logger.info(f"[CONTEXT_EXTRACTION] The first 500 act_text characters: {act_text[:500]}")
            else:
                logger.warning(f"[CONTEXT_EXTRACTION] act_text WAY FOR THE PROCESS {case_number}!")
            
            response = await _get_client().chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            response_text = response.choices[0].message.content
            logger.info(f"[CONTEXT_EXTRACTION] Response from OpenAI (first 500 characters)): {response_text[:500] if response_text else 'EMPTY'}")
            return response_text
        
        # run_async is used for simultaneous Celery
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        response_text = loop.run_until_complete(get_response())
        
        if not response_text:
            return {
                "context": "",
                "full_context": "",
                "mentions_count": 0,
                "confidence": 0.0
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
        
        # Parsim JSON Response
        try:
            result = json.loads(cleaned_text)
            
            # Check that the context does not contain prompto or instructions
            context = result.get("context", "") or result.get("full_context", "")
            if context and ('Task:' in context or 'Find all the references.' in context or 'Extract the context' in context or 'Analyze the following' in context or 'Text of the judicial act:' in context):
                # It's prompt, not context, we purify.
                result["context"] = ""
                result["full_context"] = ""
                result["mentions_count"] = 0
                result["confidence"] = 0.0
            
            logger.info(f"[CONTEXT_EXTRACTION] Successfully dislodged JSON for a case {case_number}: {result}")
            return result
        except json.JSONDecodeError as e:
            # If we failed to disperse JSON, we try to extract the data from the text directly
            logger.error(f"[CONTEXT_EXTRACTION] JSON decode error for the case {case_number}: {e}")
            logger.error(f"[CONTEXT_EXTRACTION] Response text: {response_text[:500]}")
            
            # Trying to find references in the text directly
            import re
            query_escaped = re.escape(query)
            mentions = len(re.findall(query_escaped, act_text, re.IGNORECASE)) if act_text else 0
            
            if mentions > 0:
                # Find the first mention and draw the context
                match = re.search(query_escaped, act_text, re.IGNORECASE)
                if match:
                    start = max(0, match.start() - 200)
                    end = min(len(act_text), match.end() + 200)
                    extracted_context = act_text[start:end].strip()
                    return {
                        "context": extracted_context,
                        "full_context": extracted_context,
                        "mentions_count": mentions,
                        "confidence": 0.7
                    }
            
            return {
                "context": "",
                "full_context": "",
                "mentions_count": 0,
                "confidence": 0.0
            }
            
    except Exception as e:
        logger.error(f"[CONTEXT_EXTRACTION] Error for business {case_number}: {e}", exc_info=True)
        return {
            "context": f"Errors in drawing context: {str(e)}",
            "full_context": "",
            "mentions_count": 0,
            "confidence": 0.0
        }
