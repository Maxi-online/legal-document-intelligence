import httpx
import logging
from typing import List, Dict, Optional
from models import CasebookResponse, CaseData
import base64
from fastapi import HTTPException

# Настраиваем логирование
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class PravoTechService:
    """Сервис для работы с API Casebook 3.0"""
    
    def __init__(self):
        import sys
        from pathlib import Path
        # Импортируем utils из локального каталога (в контейнере это /app/utils.py)
        # Сначала пробуем локальный utils, затем backend/utils для обратной совместимости
        try:
            from utils import (
                get_casebook_api_key, 
                get_casebook_base_url,
                get_casebook_username,
                get_casebook_password
            )
        except ImportError:
            # Fallback: пробуем импортировать из backend/utils
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from utils import (
                get_casebook_api_key, 
                get_casebook_base_url,
                get_casebook_username,
                get_casebook_password
            )
        
        self.api_key = get_casebook_api_key()  # Для обратной совместимости
        self.username = get_casebook_username()
        self.password = get_casebook_password()
        self.base_url = get_casebook_base_url()
        self.timeout = 30.0
        self._access_token: Optional[str] = None
        self._api_keys: Optional[List[str]] = None
        self._token_expires_at: Optional[float] = None
    
    def _build_auth_header(self) -> Optional[str]:
        """
        Строит заголовок авторизации для API Casebook 3.0.
        Согласно документации, API может использовать Basic Auth напрямую.
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
        Получает API ключи через POST /login согласно документации API 3.0
        https://api3.casebook.ru/api-docs/index.html#/Аутентификация/LoginPost
        
        Запрос: POST /login
        Тело: {"login": "username", "password": "password"}
        Ответ: {"apiKeys": ["key1", "key2", ...]}
        """
        import time
        
        # Проверяем, есть ли валидные ключи
        if self._api_keys and self._token_expires_at and time.time() < self._token_expires_at:
            return self._api_keys
        
        # Проверяем наличие учетных данных
        if not self.username or not self.password:
            return None
        
        # Получаем API ключи через /login endpoint согласно документации
        # Формат запроса: POST /login с телом {"login": "...", "password": "..."}
        login_data = {
            "login": self.username,  # ВАЖНО: поле называется "login", а не "username"!
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
                # POST запрос на /login согласно документации
                response = await client.post(
                    "/login",
                    json=login_data,
                    headers=headers
                )
                
                response.raise_for_status()
                auth_data = response.json()
                
                # Извлекаем API ключи из ответа согласно документации
                # Ответ: {"apiKeys": ["key1", "key2", ...]}
                api_keys = auth_data.get("apiKeys", [])
                
                if not api_keys or not isinstance(api_keys, list) or len(api_keys) == 0:
                    logger.error(f"Не удалось получить API ключи из ответа API: {auth_data}")
                    return None
                
                # Сохраняем первый ключ как основной токен для авторизации
                self._api_keys = api_keys
                self._access_token = api_keys[0] if api_keys else None
                
                # Устанавливаем время истечения (по умолчанию 1 час)
                self._token_expires_at = time.time() + 3600 - 60  # Обновляем за минуту до истечения
                
                return self._api_keys
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка аутентификации в Casebook API 3.0: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Ошибка аутентификации в Casebook API 3.0: {e.response.text[:200]}"
            )
        except Exception as e:
            logger.error(f"Ошибка при получении API ключей: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Внутренняя ошибка при получении API ключей: {str(e)}"
            )
    
    async def query_casebook(self, endpoint: str, params: Dict, method: str = "GET") -> Dict:
        """
        Выполняет запрос к API Casebook 3.0 с автоматической аутентификацией.
        
        Args:
            endpoint: Относительный путь API (например, '/api/v3/arbitration/search')
            params: Параметры запроса
            method: HTTP метод (GET, POST и т.д.)
        
        Returns:
            Ответ API в формате JSON
        
        Raises:
            HTTPException: Если учетные данные не указаны или произошла ошибка при запросе
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # Согласно документации: получаем API ключи через POST /login
        # API ключ передается в заголовке "apikey" (не Authorization!)
        api_keys = await self._get_api_keys()
        if api_keys and len(api_keys) > 0:
            # Используем первый API ключ в заголовке "apikey"
            api_key = api_keys[0]
            headers["apikey"] = api_key
        else:
            raise HTTPException(
                status_code=401,
                detail="Не удалось получить API ключи для Casebook API 3.0. Проверьте учетные данные в settings.json"
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
            logger.error(f"Timeout при запросе к Casebook API: {e}")
            raise HTTPException(
                status_code=504,
                detail=f"Timeout при запросе к Casebook API 3.0: {str(e)}"
            )
        except httpx.HTTPStatusError as e:
            # Если 401, возможно API ключ истек - пробуем обновить
            if e.response.status_code == 401:
                self._api_keys = None
                self._token_expires_at = None
                # Пробуем еще раз с новыми API ключами
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
            
            logger.error(f"HTTP ошибка при запросе к Casebook API: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Ошибка при запросе к Casebook API 3.0: {e.response.text[:200]}"
            )
        except Exception as e:
            logger.error(f"Ошибка при запросе к Casebook API: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Внутренняя ошибка при запросе к Casebook API 3.0: {str(e)}"
            )
    
    async def search_cases(self, query: str, search_type: str) -> List[Dict]:
        """
        Поиск судебных актов по запросу через Casebook API 3.0
        Согласно документации: https://api3.casebook.ru/api-docs/index.html#/
        
        Args:
            query: Поисковый запрос (ФИО, ИНН, наименование)
            search_type: Тип поиска ("fio", "inn", "company")
        
        Returns:
            Список найденных дел с метаданными
        """
        # Сохраняем query для дальнейшего сопоставления с участниками
        self._last_query = query
        """
        Поиск судебных актов по запросу через Casebook API 3.0
        Согласно документации: https://api3.casebook.ru/api-docs/index.html#/
        
        Args:
            query: Поисковый запрос (ФИО, ИНН, наименование)
            search_type: Тип поиска ("fio", "inn", "company")
        
        Returns:
            Список найденных дел с метаданными
        """
        # Согласно документации API 3.0:
        # - Для поиска по ИНН/компании: GET /arbitrage/cases
        # - Для поиска по ФИО (банкротство физлиц): GET /arbitrage/cases/citizenBankruptcy
        
        if search_type == "inn":
            # Поиск по ИНН через /arbitrage/cases
            endpoint = "/arbitrage/cases"
            params = {
                "sideInn": query,
                "size": 50,
                "page": 1,
            }
        elif search_type == "company":
            # Поиск по наименованию компании через /arbitrage/cases
            endpoint = "/arbitrage/cases"
            params = {
                "sideName": query,
                "size": 50,
                "page": 1,
            }
        else:  # fio - поиск по ФИО через банкротство физлиц
            # Парсим ФИО: предполагаем формат "Фамилия Имя Отчество" или "Фамилия И.О."
            fio_parts = query.strip().split()
            endpoint = "/arbitrage/cases/citizenBankruptcy"
            params = {
                "size": 50,
                "page": 1,
            }
            
            if len(fio_parts) >= 1:
                params["lastName"] = fio_parts[0]  # Фамилия
            if len(fio_parts) >= 2:
                params["firstName"] = fio_parts[1]  # Имя
            if len(fio_parts) >= 3:
                params["middleName"] = fio_parts[2]  # Отчество
            
            # Режим поиска по имени
            params["nameFilter"] = "fullOrShort"
        
        # Выполняем запрос к API Casebook 3.0
        data = await self.query_casebook(endpoint, params, method="GET")
        
        # Разбираем результаты
        results = self.parse_casebook_results(data)
        
        print(f"[search_cases] После parse_casebook_results: {len(results)} результатов")
        logger.info(f"[search_cases] После parse_casebook_results: {len(results)} результатов")
        
        # Получаем полный текст документов для каждого дела (асинхронно)
        # Это нужно для LLM обработки - требуется машиночитаемый текст
        print(f"[search_cases] Вызов _enrich_with_document_texts для {len(results)} результатов")
        logger.info(f"[search_cases] Вызов _enrich_with_document_texts для {len(results)} результатов")
        await self._enrich_with_document_texts(results)
        
        print(f"[search_cases] После _enrich_with_document_texts: {len(results)} результатов")
        if results:
            first_result = results[0]
            print(f"[search_cases] Первый результат после обогащения: act_text присутствует={bool(first_result.get('act_text'))}, длина={len(first_result.get('act_text', '')) if first_result.get('act_text') else 0}")
            logger.info(f"[search_cases] Первый результат после обогащения: act_text присутствует={bool(first_result.get('act_text'))}, длина={len(first_result.get('act_text', '')) if first_result.get('act_text') else 0}")
        
        return results
    
    def parse_casebook_results(self, data: Dict) -> List[Dict]:
        """
        Разбирает результаты поиска и извлекает необходимые данные из API Casebook 3.0
        Согласно документации: ответ содержит {"page": 0, "size": 0, "pages": 0, "total": 0, "items": [...]}
        
        Args:
            data: Ответ API Casebook 3.0
        
        Returns:
            Список дел с метаданными
        """
        results = []
        
        # Согласно документации API 3.0, ответ имеет структуру:
        # {"page": 0, "size": 0, "pages": 0, "total": 0, "items": [...]}
        items = data.get('items', [])
        
        # Если items пустой, но есть прямые поля, создаем один элемент
        if not items and isinstance(data, dict):
            # Проверяем, может быть это один результат
            if any(key in data for key in ['number', 'caseNumber', 'case_number']):
                items = [data]
        
        for item in items:
            # Согласно документации API 3.0, структура ответа:
            # Для /arbitrage/cases: item содержит поля number, courtName, registrationDate, sides, и т.д.
            # Для /arbitrage/cases/citizenBankruptcy: item содержит case с вложенной структурой
            
            # Обрабатываем структуру для citizenBankruptcy (вложенный case)
            case_data = item.get('case', item)  # Если есть вложенный case, используем его
            
            case_number = case_data.get('number', '')
            court = case_data.get('courtName', '')
            
            # Дата регистрации дела
            date = case_data.get('registrationDate') or case_data.get('closeDate') or ''
            
            # URL документа - формируем из caseId и documentId
            case_id = case_data.get('id', '')
            act_url = ''
            document_id = None
            if case_id:
                # Получаем ID последнего документа для формирования URL
                last_doc = case_data.get('lastDocument', {})
                if isinstance(last_doc, dict):
                    document_id = last_doc.get('id')
                    if document_id:
                        # Формируем URL для получения текста документа
                        act_url = f"{self.base_url.rstrip('/')}/arbitrage/cases/{case_id}/documents/{document_id}/text"
                    else:
                        # Fallback: список документов
                        act_url = f"{self.base_url.rstrip('/')}/arbitrage/cases/{case_id}/documents"
                else:
                    act_url = f"{self.base_url.rstrip('/')}/arbitrage/cases/{case_id}/documents"
            
            # Сохраняем document_id в metadata для использования в _enrich_with_document_texts
            # Но не используем его напрямую - всегда получаем список документов через API
            
            # Участники дела (sides)
            sides = case_data.get('sides', [])
            parties = []
            for side in sides:
                if isinstance(side, dict):
                    side_name = side.get('name', '') or side.get('shortName', '')
                    side_type = side.get('type', '')
                    if side_name:
                        parties.append(f"{side_name} ({side_type})" if side_type else side_name)
            
            # Текст решения - НЕ устанавливаем здесь, будет загружен полный текст в _enrich_with_document_texts
            act_text = ""  # Будет заменен полным текстом документа
            
            # Тип акта
            act_type = case_data.get('caseCategory', '') or case_data.get('caseTypeCode', '')
            
            # Контекст - используем описание последнего документа
            last_doc = case_data.get('lastDocument', {})
            context = last_doc.get('description', '') if isinstance(last_doc, dict) else ''
            
            # Тип участия - извлекаем из sides согласно документации API:
            # 'plaintiff' - истец, 'creditor' - кредитор, 'defendant' - ответчик,
            # 'debtor' - должник, 'thirdPerson' - третье лицо, 'other' - иное лицо
            # Ищем тип участия для конкретного запроса (query), сопоставляя с участниками
            type_of_mention = ''
            query_lower = (self._last_query or '').lower()
            
            # Ищем участника, который соответствует запросу
            matched_side_types = []
            for side in sides:
                if isinstance(side, dict):
                    side_name = (side.get('name', '') or side.get('shortName', '') or '').lower()
                    side_inn = (side.get('inn', '') or '').lower()
                    side_type = side.get('type', '')
                    
                    # Проверяем совпадение по имени или ИНН
                    if query_lower and side_type:
                        if query_lower in side_name or side_name in query_lower:
                            matched_side_types.append(side_type)
                        elif side_inn and query_lower == side_inn:
                            matched_side_types.append(side_type)
            
            # Если нашли совпадения - используем их, иначе берем все типы
            if matched_side_types:
                type_of_mention = ','.join(matched_side_types)
            elif sides:
                # Если не нашли точного совпадения, берем все типы участников
                side_types = [s.get('type', '') for s in sides if isinstance(s, dict) and s.get('type')]
                type_of_mention = ','.join(side_types) if side_types else ''
            
            # Релевантность (для citizenBankruptcy)
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
                    "document_id": document_id,  # Сохраняем для справки, но не используем напрямую
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
        Обогащает результаты полным текстом документов из API Casebook 3.0.
        Согласно документации: GET /arbitrage/cases/{caseId}/documents/{documentId}/text
        Это необходимо для LLM обработки - требуется машиночитаемый текст (не PDF).
        """
        import asyncio
        
        print(f"[_enrich_with_document_texts] Начало обогащения {len(results)} результатов")
        logger.info(f"[_enrich_with_document_texts] Начало обогащения {len(results)} результатов")
        
        async def fetch_document_text(case_id: str, document_id: str) -> Optional[str]:
            """Получает текст документа через API (машиночитаемый формат)"""
            if not case_id or not document_id:
                logger.warning(f"[fetch_document_text] Пропуск: case_id={case_id}, document_id={document_id}")
                return None
            
            try:
                logger.info(f"[fetch_document_text] Запрос текста для дела {case_id}, документ {document_id}")
                # Получаем API ключи для запросов
                api_keys = await self._get_api_keys()
                if not api_keys:
                    logger.error("[fetch_document_text] Не удалось получить API ключи")
                    return None
                
                headers = {
                    "Accept": "text/plain, application/json, */*",
                    "Content-Type": "application/json",
                    "apikey": api_keys[0]
                }
                
                # Endpoint /text возвращает текст напрямую, а не JSON!
                endpoint = f"/arbitrage/cases/{case_id}/documents/{document_id}/text"
                
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    follow_redirects=True
                ) as client:
                    response = await client.get(endpoint, headers=headers)
                    response.raise_for_status()
                    
                    # Проверяем Content-Type
                    content_type = response.headers.get("content-type", "").lower()
                    logger.info(f"[fetch_document_text] Content-Type: {content_type}")
                    
                    # Если это JSON - парсим, иначе берем как текст
                    if "application/json" in content_type:
                        try:
                            text_data = response.json()
                            if isinstance(text_data, str):
                                logger.info(f"[fetch_document_text] Текст из JSON (первые 200 символов): {text_data[:200]}")
                                return text_data
                            elif isinstance(text_data, dict):
                                text = text_data.get('text') or text_data.get('content') or text_data.get('data', '')
                                logger.info(f"[fetch_document_text] Текст из dict (первые 200 символов): {text[:200] if text else 'EMPTY'}")
                                return text
                        except Exception as json_err:
                            logger.warning(f"[fetch_document_text] Не удалось распарсить как JSON: {json_err}, пробуем как текст")
                    
                    # Берем как текст напрямую
                    text = response.text
                    text_len = len(text)
                    logger.info(f"[fetch_document_text] Получен текст напрямую, длина: {text_len} символов")
                    print(f"[fetch_document_text] Получен текст напрямую, длина: {text_len} символов")
                    if text_len > 0:
                        logger.info(f"[fetch_document_text] Первые 200 символов: {text[:200]}")
                        logger.info(f"[fetch_document_text] Последние 200 символов: {text[-200:]}")
                    return text
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"[fetch_document_text] HTTP ошибка {e.response.status_code} при получении текста документа {case_id}/{document_id}: {e.response.text[:500]}")
                return None
            except Exception as e:
                logger.error(f"[fetch_document_text] Ошибка при получении текста документа {case_id}/{document_id}: {e}", exc_info=True)
                return None
        
        # Получаем API ключи для запросов
        api_keys = await self._get_api_keys()
        if not api_keys:
            logger.error("Не удалось получить API ключи для загрузки текстов документов")
            return
        
        # Собираем задачи для параллельной загрузки текстов
        tasks = []
        for result in results:
            case_id = result.get("metadata", {}).get("case_id")
            case_number = result.get("case_number", "unknown")
            act_url = result.get("act_url", "")
            logger.info(f"[_enrich_with_document_texts] Обработка дела {case_number}, case_id={case_id}")
            if not case_id:
                logger.warning(f"[_enrich_with_document_texts] Пропуск дела {case_number}: нет case_id")
                continue
            
            # Сначала пытаемся получить document_id из metadata
            document_id = result.get("metadata", {}).get("document_id")
            if document_id:
                logger.info(f"[_enrich_with_document_texts] Найден document_id в metadata: {document_id}")
            
            # Если не нашли в metadata, пытаемся извлечь document_id из act_url (если он там есть)
            if not document_id and act_url and f"/arbitrage/cases/{case_id}/documents/" in act_url:
                # Извлекаем document_id из URL вида: .../cases/{case_id}/documents/{document_id}/text
                import re
                match = re.search(rf'/arbitrage/cases/{re.escape(case_id)}/documents/([^/]+)', act_url)
                if match:
                    document_id = match.group(1)
                    logger.info(f"[_enrich_with_document_texts] Извлечен document_id из act_url: {document_id}")
            
            # Если не нашли в URL, получаем список документов через API
            if not document_id:
                try:
                    logger.info(f"[_enrich_with_document_texts] Запрос списка документов для дела {case_id}")
                    docs_endpoint = f"/arbitrage/cases/{case_id}/documents"
                    docs_data = await self.query_casebook(docs_endpoint, {}, method="GET")
                    
                    logger.info(f"[_enrich_with_document_texts] Получен список документов, тип: {type(docs_data)}")
                    # Предполагаем, что ответ содержит список документов
                    if isinstance(docs_data, list) and len(docs_data) > 0:
                        # Берем первый документ (обычно это решение, API возвращает отсортированными)
                        first_doc = docs_data[0]
                        if isinstance(first_doc, dict):
                            document_id = first_doc.get('id')
                            logger.info(f"[_enrich_with_document_texts] Найден document_id из list: {document_id}")
                    elif isinstance(docs_data, dict):
                        items = docs_data.get('items', [])
                        logger.info(f"[_enrich_with_document_texts] Найдено документов в dict: {len(items)}")
                        if items and len(items) > 0:
                            # Берем первый документ (обычно это решение)
                            first_doc = items[0]
                            if isinstance(first_doc, dict):
                                document_id = first_doc.get('id')
                                logger.info(f"[_enrich_with_document_texts] Найден document_id из dict: {document_id}")
                except Exception as e:
                    logger.error(f"[_enrich_with_document_texts] Ошибка при получении списка документов для дела {case_id}: {e}", exc_info=True)
            
            if document_id:
                tasks.append((result, case_id, document_id))
                logger.info(f"[_enrich_with_document_texts] Добавлена задача для дела {case_number} с document_id={document_id}")
            else:
                logger.warning(f"[_enrich_with_document_texts] Не найден document_id для дела {case_number}")
        
        # Загружаем тексты параллельно (ограничиваем количество одновременных запросов)
        semaphore = asyncio.Semaphore(5)  # Максимум 5 параллельных запросов
        
        async def fetch_with_semaphore(result, case_id, document_id):
            async with semaphore:
                text = await fetch_document_text(case_id, document_id)
                if text:
                    text_len = len(text)
                    result["act_text"] = text
                    logger.info(f"[_enrich_with_document_texts] Получен полный текст документа для дела {result.get('case_number', case_id)} ({text_len} символов)")
                    print(f"[_enrich_with_document_texts] Получен полный текст документа для дела {result.get('case_number', case_id)} ({text_len} символов)")
                    if text_len < 100:
                        logger.error(f"[_enrich_with_document_texts] КРИТИЧНО: Текст слишком короткий ({text_len} символов)! LLM не сможет обработать!")
                        print(f"[_enrich_with_document_texts] КРИТИЧНО: Текст слишком короткий ({text_len} символов)! LLM не сможет обработать!")
                else:
                    logger.warning(f"[_enrich_with_document_texts] Не удалось получить текст для дела {result.get('case_number', case_id)}")
                    print(f"[_enrich_with_document_texts] Не удалось получить текст для дела {result.get('case_number', case_id)}")
        
        # Выполняем все задачи параллельно
        logger.info(f"[_enrich_with_document_texts] Всего задач для загрузки текстов: {len(tasks)}")
        if tasks:
            await asyncio.gather(*[fetch_with_semaphore(r, cid, did) for r, cid, did in tasks], return_exceptions=True)
