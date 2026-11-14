import httpx
import logging
from typing import List, Dict, Optional
from models import CasebookResponse, CaseData
import base64
from fastapi import HTTPException

# Adjusting Login
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class PravoTechService:
    'Service for API Casebook 3.0'
    
    def __init__(self):
        import sys
        from pathlib import Path
        # Import utils from local catalogue (in container is /app/utils.py))
        # First try local utils, then backend/utils for interoperability
        try:
            from utils import (
                get_casebook_api_key, 
                get_casebook_base_url,
                get_casebook_username,
                get_casebook_password
            )
        except ImportError:
            # Fallback: Try to import from backend/utils
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from utils import (
                get_casebook_api_key, 
                get_casebook_base_url,
                get_casebook_username,
                get_casebook_password
            )
        
        self.api_key = get_casebook_api_key()  # For inverse compatibility
        self.username = get_casebook_username()
        self.password = get_casebook_password()
        self.base_url = get_casebook_base_url()
        self.timeout = 30.0
        self._access_token: Optional[str] = None
        self._api_keys: Optional[List[str]] = None
        self._token_expires_at: Optional[float] = None
    
    def _build_auth_header(self) -> Optional[str]:
        """
        ==History==He is building an authorship title for the API Casebook 3.0.
        According to the documentation, API can use Basic Auth directly.
        """
        if self.username and self.password:
            credentials = f"{self.username}:{self.password}"
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
            return f"Basic {encoded}"
        elif self.api_key:
            return f"Bearer {self.api_key}"
        return None
    
    async def _get_api_keys(self) -> Optional[List[str]]:
        """
        Receives API keys via POST /login according to API 3.0 documentation
        https://api3.casebook.ru/api-docs/index.html#/Authentication/LoginPost
        
        Request: POST / Login
        Body: {"login": "username", "password": "password"}
        Response: {"apiKeys": ["key1", "key2", ...]}
        """
        import time
        
        # Check to see if there's any valid keys.
        if self._api_keys and self._token_expires_at and time.time() < self._token_expires_at:
            return self._api_keys
        
        # Checking the existence of accounting data
        if not self.username or not self.password:
            return None
        
        # Get API keys through /login endpoint according to documentation
        # Request format: POST /login with body {"login": "...", "password"": "..."}
        login_data = {
            "login": self.username,  # IMPORTANT: The field is called "login," not "username"!
            "password": self.password
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=True
            ) as client:
                # POST request for /login according to documentation
                response = await client.post(
                    "/login",
                    json=login_data,
                    headers=headers
                )
                
                response.raise_for_status()
                auth_data = response.json()
                
                # We extract API keys from the answer according to the documentation
                # Response: {"apiKeys": ["key1", "key2", ...]}
                api_keys = auth_data.get("apiKeys", [])
                
                if not api_keys or not isinstance(api_keys, list) or len(api_keys) == 0:
                    logger.error(f"Could not obtain the API keys from the API response: {auth_data}")
                    return None
                
                # Save the first key as the main current for authorization
                self._api_keys = api_keys
                self._access_token = api_keys[0] if api_keys else None
                
                # Set expiration time (default 1 hour)
                self._token_expires_at = time.time() + 3600 - 60  # We'll update it a minute before it's over.
                
                return self._api_keys
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Configuration error in Casebook API 3.0: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Configuration error in Casebook API 3.0: {e.response.text[:200]}"
            )
        except Exception as e:
            logger.error(f"Error in receiving API keys: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Internal error when receiving API keys: {str(e)}"
            )
    
    async def query_casebook(self, endpoint: str, params: Dict, method: str = "GET") -> Dict:
        """
        Performs an API Casebook 3.0 with automatic authentication.
        
        Args:
            endpoint: Relative path API (e.g. '/api/v3/arbitration/search')
            params: Query parameters
            method: HTTP method (GT, POST, etc.)
        
        Returns:
            API response in JSON format
        
        Raises:
            HTTPException: If the account data is not specified or an error has occurred when requested
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # According to the documentation: API receives keys via POST /login
        # The API key is transmitted in the title "apikey" (not "Authorization")!)
        api_keys = await self._get_api_keys()
        if api_keys and len(api_keys) > 0:
            # We use the first API key in the "apikey" title.
            api_key = api_keys[0]
            headers["apikey"] = api_key
        else:
            raise HTTPException(
                status_code=401,
                detail='Could not obtain API keys for Casebook API 3.0. Check settings.json records'
            )
        
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, 
                timeout=self.timeout,
                follow_redirects=True
            ) as client:
                if method.upper() == "POST":
                    response = await client.post(endpoint, json=params, headers=headers)
                else:
                    response = await client.get(endpoint, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            logger.error(f"Timeout on Casebook API request: {e}")
            raise HTTPException(
                status_code=504,
                detail=f"Timeout on request to Casebook API 3.0: {str(e)}"
            )
        except httpx.HTTPStatusError as e:
            # If 401, maybe the API key has expired, we're trying to update it.
            if e.response.status_code == 401:
                self._api_keys = None
                self._token_expires_at = None
                # Try again with the new API keys.
                api_keys = await self._get_api_keys()
                if api_keys and len(api_keys) > 0:
                    headers["apikey"] = api_keys[0]
                    try:
                        async with httpx.AsyncClient(
                            base_url=self.base_url,
                            timeout=self.timeout,
                            follow_redirects=True
                        ) as client:
                            if method.upper() == "POST":
                                response = await client.post(endpoint, json=params, headers=headers)
                            else:
                                response = await client.get(endpoint, params=params, headers=headers)
                            response.raise_for_status()
                            return response.json()
                    except Exception:
                        pass
            
            logger.error(f"HTTP error when requesting a Casebook API: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Error when requesting the Casebook API 3.0: {e.response.text[:200]}"
            )
        except Exception as e:
            logger.error(f"Error when requesting the Casebook API: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Internal error when requesting the Casebook API 3.0: {str(e)}"
            )
    
    async def search_cases(self, query: str, search_type: str) -> List[Dict]:
        """
        Search for court actions on request through Casebook API 3.0
        According to the documentation: https://api3.casebook.ru/api-docs/index.html#/
        
        Args:
            query: Search request (FIO, INN, name)
            search_type: Search type ("fio", "inn", "company")
        
        Returns:
            List of metadata cases found
        """
        # Save quary for further comparison with participants
        self._last_query = query
        '\n        Search for court actions on request through Casebook API 3.0\n        According to the documentation: https://api3.casebook.ru/api-docs/index.html#/\n        \n        Args:\n            query: Search request (FIO, INN, name)\n            search_type: Search type ("fio", "inn", "company")\n        \n        Returns:\n            List of metadata cases found\n        '
        # According to API 3.0:
        # - For INN/companie search: GET /arbitrage/cases
        # - For FIO search (Physician Bancroticity): GET /arbitrage/cases/citizenBankruptcy
        
        if search_type == "inn":
            # /arbitrage/cases search
            endpoint = "/arbitrage/cases"
            params = {
                "sideInn": query,
                "size": 50,
                "page": 1,
            }
        elif search_type == "company":
            # /arbitrage/cases company name search
            endpoint = "/arbitrage/cases"
            params = {
                "sideName": query,
                "size": 50,
                "page": 1,
            }
        else:  # fio - FIO search through bankruptcy of physicals
            # Parsim FIO: The intended format is "Father's name" or "I.O.'s family name"."
            fio_parts = query.strip().split()
            endpoint = "/arbitrage/cases/citizenBankruptcy"
            params = {
                "size": 50,
                "page": 1,
            }
            
            if len(fio_parts) >= 1:
                params["lastName"] = fio_parts[0]  # Name
            if len(fio_parts) >= 2:
                params["firstName"] = fio_parts[1]  # Name
            if len(fio_parts) >= 3:
                params["middleName"] = fio_parts[2]  # Fatherhood
            
            # Search mode by name
            params["nameFilter"] = "fullOrShort"
        
        # Request for API Casebook 3.0
        data = await self.query_casebook(endpoint, params, method="GET")
        
        # Parse the results
        results = self.parse_casebook_results(data)
        
        print(f"[search_cases] After parse_casebook_results: {len(results)} Results")
        logger.info(f"[search_cases] After parse_casebook_results: {len(results)} Results")
        
        # Get the full text of the documents for each case (asynchronous))
        # This is for LLM processing - machine readable text required
        print(f"[search_cases] Challenge _enrich_with_document_texts {len(results)} Results")
        logger.info(f"[search_cases] Challenge _enrich_with_document_texts {len(results)} Results")
        await self._enrich_with_document_texts(results)
        
        print(f"[search_cases] After _enrich_with_document_texts: {len(results)} Results")
        if results:
            first_result = results[0]
            print(f"[search_cases] First result after enrichment: act_text is present={bool(first_result.get('act_text'))}, length={len(first_result.get('act_text', '')) if first_result.get('act_text') else 0}")
            logger.info(f"[search_cases] First result after enrichment: act_text is present={bool(first_result.get('act_text'))}, length={len(first_result.get('act_text', '')) if first_result.get('act_text') else 0}")
        
        return results
    
    def parse_casebook_results(self, data: Dict) -> List[Dict]:
        """
        Understand search results and extract the necessary data from the Casebook 3.0 API
        According to the documentation: the reply contains {"page": 0, "size": 0, "pages": 0, "total": 0, "items": [...]}
        
        Args:
            data: Response API Casebook 3.0
        
        Returns:
            List of metadata cases
        """
        results = []
        
        # According to API 3.0, the response is structured as follows:
        # {"page": 0, "size": 0, "pages": 0, "total": 0, "items": [...]}
        items = data.get('items', [])
        
        # If items are empty, but there are straight fields, create one element
        if not items and isinstance(data, dict):
            # See if it's one result.
            if any(key in data for key in ['number', 'caseNumber', 'case_number']):
                items = [data]
        
        for item in items:
            # According to API 3.0, the structure of the reply:
            # For /arbitrage/cases: it contains number, court Name, registrationDate, slides, etc.
            # For /arbitrage/cases/citizenBankruptcy: item contains case with attached structure
            
            # Process the structure for CitazenBankruptcy)
            case_data = item.get('case', item)  # If there's a case, use it.
            
            case_number = case_data.get('number', '')
            court = case_data.get('courtName', '')
            
            # Date of registration of case
            date = case_data.get('registrationDate') or case_data.get('closeDate') or ''
            
            # UrL Document - Formed from CaseId and DocumentId
            case_id = case_data.get('id', '')
            act_url = ''
            document_id = None
            if case_id:
                # Get the ID of the last document to form a URL.
                last_doc = case_data.get('lastDocument', {})
                if isinstance(last_doc, dict):
                    document_id = last_doc.get('id')
                    if document_id:
                        # Set up an ORL to obtain the text of the document
                        act_url = f"{self.base_url.rstrip('/')}/arbitrage/cases/{case_id}/documents/{document_id}/text"
                    else:
                        # Fallback: List of documents
                        act_url = f"{self.base_url.rstrip('/')}/arbitrage/cases/{case_id}/documents"
                else:
                    act_url = f"{self.base_url.rstrip('/')}/arbitrage/cases/{case_id}/documents"
            
            # Save document_id in metadata for use in _enrich_with_document_texts
            # But we don't use it directly-- always get a list of documents through API
            
            # Participants in the case (sides)
            sides = case_data.get('sides', [])
            parties = []
            for side in sides:
                if isinstance(side, dict):
                    side_name = side.get('name', '') or side.get('shortName', '')
                    side_type = side.get('type', '')
                    if side_name:
                        parties.append(f"{side_name} ({side_type})" if side_type else side_name)
            
            # Decision text - Not set here, full text will be downloaded at _enrich_with_document_texts
            act_text = ""  # To be replaced by the full text
            
            # Type of act
            act_type = case_data.get('caseCategory', '') or case_data.get('caseTypeCode', '')
            
            # Context - last document description used
            last_doc = case_data.get('lastDocument', {})
            context = last_doc.get('description', '') if isinstance(last_doc, dict) else ''
            
            # Type of participation - extract from sides according to API documentation:
            # 'billiff' is the plaintiff, 'creditor' is the creditor, 'defendant' is the defendant,
            # 'Debtor's the debtor, 'thirdPerson' is the third person, 'other' is the other person
            # Looking for the type of participation for a specific request (query), comparing with participants
            type_of_mention = ''
            query_lower = (self._last_query or '').lower()
            
            # Looking for a participant who meets the request
            matched_side_types = []
            for side in sides:
                if isinstance(side, dict):
                    side_name = (side.get('name', '') or side.get('shortName', '') or '').lower()
                    side_inn = (side.get('inn', '') or '').lower()
                    side_type = side.get('type', '')
                    
                    # Checking a match by name or I.N.
                    if query_lower and side_type:
                        if query_lower in side_name or side_name in query_lower:
                            matched_side_types.append(side_type)
                        elif side_inn and query_lower == side_inn:
                            matched_side_types.append(side_type)
            
            # If we find a match, we use it, or we take all types
            if matched_side_types:
                type_of_mention = ','.join(matched_side_types)
            elif sides:
                # If we don't find a exact match, we take all types of participants
                side_types = [s.get('type', '') for s in sides if isinstance(s, dict) and s.get('type')]
                type_of_mention = ','.join(side_types) if side_types else ''
            
            # Relevance (for CitienBankruptcy)
            relevance = item.get('relevance', '')
            
            result = {
                "case_number": case_number,
                "court": court,
                "date": date,
                "act_url": act_url,
                "parties": parties,
                "act_text": act_text or "",
                "act_type": act_type,
                "context": context or "",
                "type_of_mention": type_of_mention or "",
                "metadata": {
                    "case_id": case_id,
                    "document_id": document_id,  # Saved for reference but not directly used
                    "case_state": case_data.get('caseState', ''),
                    "case_type_code": case_data.get('caseTypeCode', ''),
                    "claim_sum": case_data.get('claimSum', 0),
                    "relevance": relevance,
                    "total": data.get('total', 0),
                }
            }
            results.append(result)
        
        return results
    
    async def _enrich_with_document_texts(self, results: List[Dict]) -> None:
        """
        Enrichs the results with the full text of documents from the API Casebook 3.0.
        According to the documentation:GET /arbitrage/cases/{caseId}/documents/{documentId}/text
        This is necessary for LLM processing - machine-readable text is required (not PDF)).
        """
        import asyncio
        
        print(f"[Inrich_with_document_texts] Start of enrichment {len(results)} Results")
        logger.info(f"[Inrich_with_document_texts] Start of enrichment {len(results)} Results")
        
        async def fetch_document_text(case_id: str, document_id: str) -> Optional[str]:
            'Receives document text via API (machine readable format))'
            if not case_id or not document_id:
                logger.warning(f"[fetch_document_text] Pass: case_id={case_id}, document_id={document_id}")
                return None
            
            try:
                logger.info(f"[fetch_document_text] Requesting text for case {case_id}document {document_id}")
                # Getting APl keys for queries.
                api_keys = await self._get_api_keys()
                if not api_keys:
                    logger.error('[fetch_document_text] Could not obtain API keys')
                    return None
                
                headers = {
                    "Accept": "text/plain, application/json, */*",
                    "Content-Type": "application/json",
                    "apikey": api_keys[0]
                }
                
                # Endpoint /text returns the text directly, not JSON!
                endpoint = f"/arbitrage/cases/{case_id}/documents/{document_id}/text"
                
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    follow_redirects=True
                ) as client:
                    response = await client.get(endpoint, headers=headers)
                    response.raise_for_status()
                    
                    # Checking Continental-Type
                    content_type = response.headers.get("content-type", "").lower()
                    logger.info(f"[fetch_document_text] Content-Type: {content_type}")
                    
                    # If it's JSON, it's parsim, or we'll take it as text.
                    if "application/json" in content_type:
                        try:
                            text_data = response.json()
                            if isinstance(text_data, str):
                                logger.info(f"[fetch_document_text] Text from JSON (first 200 characters)): {text_data[:200]}")
                                return text_data
                            elif isinstance(text_data, dict):
                                text = text_data.get('text') or text_data.get('content') or text_data.get('data', '')
                                logger.info(f"[fetch_document_text] Text from dict (first 200 characters)): {text[:200] if text else 'EMPTY'}")
                                return text
                        except Exception as json_err:
                            logger.warning(f"[fetch_document_text] Could not unsolved as JSON: {json_err}, let's try it as a text.")
                    
                    # Take it directly.
                    text = response.text
                    text_len = len(text)
                    logger.info(f"[fetch_document_text] Text received directly, length: {text_len} Symbols")
                    print(f"[fetch_document_text] Text received directly, length: {text_len} Symbols")
                    if text_len > 0:
                        logger.info(f"[fetch_document_text] First 200 characters: {text[:200]}")
                        logger.info(f"[fetch_document_text] Last 200 characters: {text[-200:]}")
                    return text
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"[fetch_document_text] HTTP error {e.response.status_code} upon receipt of the text of the document {case_id}/{document_id}: {e.response.text[:500]}")
                return None
            except Exception as e:
                logger.error(f"[fetch_document_text] Error when receiving the text of the document {case_id}/{document_id}: {e}", exc_info=True)
                return None
        
        # Getting APl keys for queries.
        api_keys = await self._get_api_keys()
        if not api_keys:
            logger.error('Unable to obtain API document download keys')
            return
        
        # Gather tasks for simultaneous downloading of texts
        tasks = []
        for result in results:
            case_id = result.get("metadata", {}).get("case_id")
            case_number = result.get("case_number", "unknown")
            act_url = result.get("act_url", "")
            logger.info(f"[Inrich_with_document_texts] Case processing {case_number}, case_id={case_id}")
            if not case_id:
                logger.warning(f"[Enrich_with_document_texts] Case pass {case_number}: no case_id")
                continue
            
            # First we try to get document_id from metadata
            document_id = result.get("metadata", {}).get("document_id")
            if document_id:
                logger.info(f"[_enrich_with_document_texts] Found document_id in metadata: {document_id}")
            
            # If not found in the metadata, we try to extract document_id from act_url (if it is there)
            if not document_id and act_url and f"/arbitrage/cases/{case_id}/documents/" in act_url:
                # We extract document_id from the URL type: .../cases/{case_id}/documents/{document_id}/text
                import re
                match = re.search(rf'/arbitrage/cases/{re.escape(case_id)}/documents/([^/]+)', act_url)
                if match:
                    document_id = match.group(1)
                    logger.info(f"[_enrich_with_document_texts] Extracted document_id from act_url: {document_id}")
            
            # If they didn't find it in the URL, they get a list of documents through the APl
            if not document_id:
                try:
                    logger.info(f"[_enrich_with_document_texts] Request for list of documents for case {case_id}")
                    docs_endpoint = f"/arbitrage/cases/{case_id}/documents"
                    docs_data = await self.query_casebook(docs_endpoint, {}, method="GET")
                    
                    logger.info(f"[_enrich_with_document_texts] List of documents received, type: {type(docs_data)}")
                    # We assume the answer contains a list of documents.
                    if isinstance(docs_data, list) and len(docs_data) > 0:
                        # Take the first document (usually this decision, API returns sorted)
                        first_doc = docs_data[0]
                        if isinstance(first_doc, dict):
                            document_id = first_doc.get('id')
                            logger.info(f"[_enrich_with_document_texts] Found document_id from list: {document_id}")
                    elif isinstance(docs_data, dict):
                        items = docs_data.get('items', [])
                        logger.info(f"[Enrich_with_document_texts] Documents found in dict: {len(items)}")
                        if items and len(items) > 0:
                            # Take the first document (usually the decision)
                            first_doc = items[0]
                            if isinstance(first_doc, dict):
                                document_id = first_doc.get('id')
                                logger.info(f"[_enrich_with_document_texts] Found document_id from dict: {document_id}")
                except Exception as e:
                    logger.error(f"[_enrich_with_document_texts] Error when receiving a list of documents for the case {case_id}: {e}", exc_info=True)
            
            if document_id:
                tasks.append((result, case_id, document_id))
                logger.info(f"[Inrich_with_document_texts] Added task for case {case_number} with document_id={document_id}")
            else:
                logger.warning(f"[_enrich_with_document_texts] Not found document_id for case {case_number}")
        
        # Load the text in parallel (limit the number of simultaneous requests))
        semaphore = asyncio.Semaphore(5)  # A maximum of 5 parallel requests
        
        async def fetch_with_semaphore(result, case_id, document_id):
            async with semaphore:
                text = await fetch_document_text(case_id, document_id)
                if text:
                    text_len = len(text)
                    result["act_text"] = text
                    logger.info(f"[_enrich_with_document_texts] Full document for case received {result.get('case_number', case_id)} ({text_len} symbols)")
                    print(f"[_enrich_with_document_texts] Full document for case received {result.get('case_number', case_id)} ({text_len} symbols)")
                    if text_len < 100:
                        logger.error(f"[_enrich_with_document_texts] CRITICAL: Text too short ({text_len} Symbols)! LLM will not be able to process!")
                        print(f"[_enrich_with_document_texts] CRITICAL: Text too short ({text_len} Symbols)! LLM will not be able to process!")
                else:
                    logger.warning(f"[_enrich_with_document_texts] Could not obtain text for case {result.get('case_number', case_id)}")
                    print(f"[_enrich_with_document_texts] Could not obtain text for case {result.get('case_number', case_id)}")
        
        # Perform all the tasks in parallel.
        logger.info(f"[_enrich_with_document_texts] Total tasks for downloading texts: {len(tasks)}")
        if tasks:
            await asyncio.gather(*[fetch_with_semaphore(r, cid, did) for r, cid, did in tasks], return_exceptions=True)
