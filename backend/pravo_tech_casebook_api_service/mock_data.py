"""
Модуль с фейковыми данными для тестирования системы
Используется для тестирования агентов обработки и настройки других модулей
"""

from typing import List, Dict
import random
from datetime import datetime, timedelta
import os
import hashlib
import re

def _stable_seed(*parts: str) -> int:
    raw = "|".join([p or "" for p in parts]).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)

def _tokenize_text(v: str) -> str:
    return (v or "").strip()

def _query_variants(query: str, search_type: str) -> List[str]:
    q = _tokenize_text(query)
    if not q:
        return [""]

    if search_type == "inn":
        digits = re.sub(r"\D+", "", q)
        if not digits:
            return [q]
        # варианты форматирования ИНН
        spaced = " ".join([digits[i:i+3] for i in range(0, len(digits), 3)])
        return [digits, f"ИНН {digits}", f"ИНН: {digits}", spaced, f"ИНН {spaced}"]

    # fio/company — варианты написания
    variants = [q]
    # кавычки для ООО
    variants.append(q.replace('"', '«').replace('"', '»'))
    variants.append(q.replace("ООО", "Общество с ограниченной ответственностью"))
    variants.append(q.replace("Общество с ограниченной ответственностью", "ООО"))
    # сокращения ФИО
    parts = q.split()
    if len(parts) >= 2:
        variants.append(f"{parts[0]} {parts[1][0]}.")
    if len(parts) >= 3:
        variants.append(f"{parts[0]} {parts[1][0]}.{parts[2][0]}.")
    # лёгкая “опечатка”
    if len(q) > 6:
        variants.append(q[:-1])
    # уникализируем
    out = []
    for v in variants:
        if v and v not in out:
            out.append(v)
    return out or [q]

from typing import Optional

def generate_mock_casebook_response(query: str, search_type: str = "fio", count: int = 10, rng: Optional[random.Random] = None, reference_time: Optional[datetime] = None) -> Dict:
    """
    Генерация фейкового ответа от Casebook API для тестирования
    
    Args:
        query: Поисковый запрос (ФИО, ИНН, наименование)
        search_type: Тип поиска ("fio", "inn", "company")
        count: Количество результатов для генерации
    
    Returns:
        Словарь с структурой ответа Casebook API
    """
    rng = rng or random
    reference_time = reference_time or datetime.now()

    courts = [
        "Арбитражный суд города Москвы",
        "Арбитражный суд Московской области",
        "Арбитражный суд города Санкт-Петербурга и Ленинградской области",
        "Арбитражный суд Московского округа",
        "Арбитражный суд Центрального округа",
        "Арбитражный суд Северо-Западного округа",
        "Арбитражный суд Поволжского округа",
        "Арбитражный суд Уральского округа",
        "Арбитражный суд Сибирского округа",
        "Арбитражный суд Дальневосточного округа",
    ]
    
    regions = [
        "Москва", "Московская область", "Санкт-Петербург", "Ленинградская область",
        "Новосибирская область", "Екатеринбург", "Нижний Новгород", "Казань",
        "Краснодарский край", "Пермский край"
    ]
    
    act_types = ["Решение", "Определение", "Постановление", "Приказ"]
    
    mention_types = ["истец", "ответчик", "участник", "контрагент", "третье лицо", "упоминание"]

    q_variants = _query_variants(query, search_type)
    
    items = []
    
    for i in range(count):
        # Генерируем случайную дату в последние 3 года
        days_ago = rng.randint(0, 1095)
        case_date = (reference_time - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        
        # Генерируем номер дела
        case_number = f"А{rng.randint(40, 75)}-{rng.randint(10000, 99999)}/{2021 + rng.randint(0, 3)}"
        
        court = rng.choice(courts)
        region = rng.choice(regions)
        act_type = rng.choice(act_types)
        mention_type = rng.choice(mention_types)

        qv1 = rng.choice(q_variants)
        qv2 = rng.choice(q_variants)
        qv3 = rng.choice(q_variants)
        
        # Генерируем контекст в зависимости от типа упоминания
        if mention_type == "истец":
            context_text = f"Установлено, что {qv1} обратился в суд с иском о взыскании задолженности в размере {rng.randint(100000, 5000000)} рублей. В обоснование требований {qv2} сослался на переписку и акт сверки. Суд удовлетворил требования частично."
            parties = [f"Истец: {qv1}", f"Ответчик: ООО 'Компания {rng.randint(1, 300)}'"]
        elif mention_type == "ответчик":
            context_text = f"Суд рассмотрел дело по иску к {qv1} о взыскании задолженности по договору. {qv2} не признал требования, указал на отсутствие поставки и заявил о зачёте. В тексте акта {qv3} упоминается неоднократно."
            parties = [f"Истец: ООО 'Компания {rng.randint(1, 300)}'", f"Ответчик: {qv1}"]
        elif mention_type == "участник":
            context_text = f"К участию в деле привлечён {qv1} в качестве третьего лица. {qv2} представил пояснения, указал на аффилированность сторон и заявил самостоятельные требования относительно предмета спора."
            parties = [
                f"Истец: ООО 'Компания {rng.randint(1, 300)}'",
                f"Ответчик: ООО 'Компания {rng.randint(301, 600)}'",
                f"Третье лицо: {qv1}"
            ]
        elif mention_type == "контрагент":
            context_text = f"В материалах дела представлен договор, заключённый между ответчиком и {qv1}. {qv2} указан в договоре как контрагент. Также в приложениях к договору встречается {qv3}."
            parties = [
                f"Истец: ООО 'Компания {rng.randint(1, 300)}'",
                f"Ответчик: ООО 'Компания {rng.randint(301, 600)}'"
            ]
        else:
            context_text = f"В тексте судебного акта упоминается {qv1}. Информация о {qv2} содержится в материалах дела, переписке и приложениях. Дополнительно встречается {qv3}, но лицо не привлечено к участию."
            parties = [
                f"Истец: ООО 'Компания {rng.randint(1, 300)}'",
                f"Ответчик: ООО 'Компания {rng.randint(301, 600)}'"
            ]
        
        # Полный текст акта (сокращенный)
        # Добавляем множественные упоминания и “шум”, чтобы проверить: BM25, embeddings, подсветку, дедуп.
        mentions_count = rng.randint(1, 12)
        mention_line = " ".join([rng.choice(q_variants) for _ in range(min(mentions_count, 6))])
        act_text = f"""
{act_type.upper()}

{case_number}

{court}

{case_date}

{context_text}

В результате рассмотрения дела суд установил следующие обстоятельства. 
В материалах дела имеются документы, подтверждающие факты, изложенные в исковом заявлении.
Упоминания (контроль): {mention_line}.
Для полнотекстового поиска: сторона/участник/контрагент/упоминание.
Суд считает необходимым удовлетворить требования истца.

РЕШИЛ:
Взыскать с ответчика в пользу истца {rng.randint(100000, 5000000)} рублей.
""".strip()
        
        public_base = os.getenv("PUBLIC_ACT_BASE_URL", "http://localhost:8000/api/acts")
        act_id = f"{case_number.replace('/', '-')}-{i+1}"

        item = {
            "case_number": case_number,
            "court_name": court,
            "date": case_date,
            # В моковом режиме указываем URL на наш gateway, чтобы работало "скачать акт" и "скачать все файлы".
            "url": f"{public_base}/{act_id}/download",
            "parties": parties,
            "text": act_text,
            "content": act_text,
            "act_type": act_type,
            "type": act_type,
            "context": context_text,
            "type_of_mention": mention_type,
            "region": region,
            "category": "Гражданские дела",
            "mentions_count": mentions_count,  # Количество упоминаний в тексте
        }
        
        items.append(item)
    
    return {
        "items": items,
        "total": len(items),
        "limit": count,
        "offset": 0
    }


def get_extended_mock_data(query: str, search_type: str = "fio") -> Dict:
    """
    Расширенные фейковые данные для комплексного тестирования
    Включает различные сценарии упоминаний
    """
    # Масштабируем моковые данные, чтобы “наверняка” показать работу ранжирования/подсветки/LLM-topN.
    # Детерминированно от (query, search_type) — чтобы тесты были повторяемыми.
    seed = _stable_seed(query, search_type)
    rng = random.Random(seed)

    items: List[Dict] = []
    
    # Сценарий 1: Истец
    items.append({
        "case_number": "А40-12345/2024",
        "court_name": "Арбитражный суд города Москвы",
        "date": "2024-01-15",
        "url": "https://casebook.ru/cases/A40-12345-2024",
        "parties": [f"Истец: {query}", "Ответчик: ООО 'Пример Компания'"],
        "text": f"{query} обратился в суд с иском о взыскании задолженности по договору поставки. {query} представил доказательства. Суд удовлетворил требования частично.",
        "content": f"{query} обратился в суд с иском о взыскании задолженности по договору поставки. {query} представил доказательства. Суд удовлетворил требования частично.",
        "act_type": "Решение",
        "type": "Решение",
        "context": f"В судебном заседании установлено, что {query} обратился в суд с иском.",
        "type_of_mention": "истец",
        "region": "Москва",
        "category": "Гражданские дела",
        "mentions_count": 3,
    })
    
    # Сценарий 2: Ответчик
    items.append({
        "case_number": "А41-67890/2024",
        "court_name": "Арбитражный суд Московской области",
        "date": "2024-02-20",
        "url": "https://casebook.ru/cases/A41-67890-2024",
        "parties": ["Истец: ООО 'Другая Компания'", f"Ответчик: {query}"],
        "text": f"Суд рассмотрел дело по иску к {query} о взыскании задолженности. {query} не признал требования.",
        "content": f"Суд рассмотрел дело по иску к {query} о взыскании задолженности. {query} не признал требования.",
        "act_type": "Решение",
        "type": "Решение",
        "context": f"К {query} предъявлен иск о взыскании задолженности.",
        "type_of_mention": "ответчик",
        "region": "Московская область",
        "category": "Гражданские дела",
        "mentions_count": 5,
    })
    
    # Сценарий 3: Участник (третье лицо)
    items.append({
        "case_number": "А50-11111/2023",
        "court_name": "Арбитражный суд Пермского края",
        "date": "2023-12-10",
        "url": "https://casebook.ru/cases/A50-11111-2023",
        "parties": [
            "Истец: ИП Иванов И.И.",
            "Ответчик: ООО 'Третья Компания'",
            f"Третье лицо: {query}"
        ],
        "text": f"В деле участвует {query} в качестве третьего лица. {query} заявил самостоятельные требования.",
        "content": f"В деле участвует {query} в качестве третьего лица. {query} заявил самостоятельные требования.",
        "act_type": "Определение",
        "type": "Определение",
        "context": f"{query} привлечен к участию в деле в качестве третьего лица.",
        "type_of_mention": "участник",
        "region": "Пермский край",
        "category": "Гражданские дела",
        "mentions_count": 2,
    })
    
    # Сценарий 4: Контрагент (упоминание в договоре)
    items.append({
        "case_number": "А43-22222/2024",
        "court_name": "Арбитражный суд города Санкт-Петербурга и Ленинградской области",
        "date": "2024-03-05",
        "url": "https://casebook.ru/cases/A43-22222-2024",
        "parties": ["Истец: ООО 'Компания А'", "Ответчик: ООО 'Компания Б'"],
        "text": f"В материалах дела имеется договор, заключенный между ответчиком и {query}. {query} указан в договоре как контрагент.",
        "content": f"В материалах дела имеется договор, заключенный между ответчиком и {query}. {query} указан в договоре как контрагент.",
        "act_type": "Решение",
        "type": "Решение",
        "context": f"{query} является контрагентом по договору, заключенному между сторонами спора.",
        "type_of_mention": "контрагент",
        "region": "Санкт-Петербург",
        "category": "Гражданские дела",
        "mentions_count": 4,
    })
    
    # Сценарий 5: Простое упоминание (не участник)
    items.append({
        "case_number": "А55-33333/2023",
        "court_name": "Арбитражный суд Свердловской области",
        "date": "2023-11-18",
        "url": "https://casebook.ru/cases/A55-33333-2023",
        "parties": ["Истец: ООО 'Компания В'", "Ответчик: ООО 'Компания Г'"],
        "text": f"В тексте судебного акта упоминается {query}. {query} фигурирует в переписке между сторонами, но не является участником дела.",
        "content": f"В тексте судебного акта упоминается {query}. {query} фигурирует в переписке между сторонами, но не является участником дела.",
        "act_type": "Определение",
        "type": "Определение",
        "context": f"{query} упоминается в материалах дела, но не является стороной спора.",
        "type_of_mention": "упоминание",
        "region": "Свердловская область",
        "category": "Гражданские дела",
        "mentions_count": 2,
    })

    # Генерируем “массу” дополнительных данных
    base_count = int(os.getenv("MOCK_RESULTS_COUNT", "80"))
    base_count = max(20, min(base_count, 250))

    generated = generate_mock_casebook_response(query=query, search_type=search_type, count=base_count, rng=rng)
    items.extend(generated.get("items", []))

    # Добавляем несколько актов по одному делу (чтобы увидеть группировку/дедуп по URL, а не по номеру дела)
    if items:
        for k in range(3):
            src = rng.choice(items)
            clone = dict(src)
            clone["act_type"] = rng.choice(["Определение", "Постановление", "Решение"])
            clone["type"] = clone["act_type"]
            clone["date"] = (datetime.now() - timedelta(days=rng.randint(0, 600))).strftime("%Y-%m-%d")
            clone["url"] = f"{src.get('url','')}/followup-{k+1}"
            clone["context"] = f"Дополнительный акт по делу {clone.get('case_number','')}: {clone.get('context','')}"
            clone["mentions_count"] = int(src.get("mentions_count", 1)) + rng.randint(0, 3)
            items.append(clone)

    # Контрольный дубликат URL (проверка дедупликации)
    if len(items) >= 5:
        dupe_src = items[1]
        dupe = dict(dupe_src)
        dupe["mentions_count"] = int(dupe.get("mentions_count", 1)) + 1
        dupe["context"] = f"{dupe.get('context','')} (дубликат для проверки дедупликации)"
        # тот же url => должен дедупнуться
        items.append(dupe)

    # Нормализуем лимит/total
    return {
        "items": items,
        "total": len(items),
        "limit": len(items),
        "offset": 0
    }
