"""
Fake data module for system testing
Used to test processing agents and settings of other modules
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
        # OSI formatting options
        spaced = " ".join([digits[i:i+3] for i in range(0, len(digits), 3)])
        return [digits, f"INN {digits}", f"INN: {digits}", spaced, f"INN {spaced}"]

    # fio/company is a writing version
    variants = [q]
    # Quantities for GS
    variants.append(q.replace('"', '«').replace('"', '»'))
    variants.append(q.replace("ООО", "Общество с ограниченной ответственностью"))
    variants.append(q.replace("Общество с ограниченной ответственностью", "ООО"))
    # FIO reduction
    parts = q.split()
    if len(parts) >= 2:
        variants.append(f"{parts[0]} {parts[1][0]}.")
    if len(parts) >= 3:
        variants.append(f"{parts[0]} {parts[1][0]}.{parts[2][0]}.")
    # Easy typing
    if len(q) > 6:
        variants.append(q[:-1])
    # deduplicate
    out = []
    for v in variants:
        if v and v not in out:
            out.append(v)
    return out or [q]

from typing import Optional

def generate_mock_casebook_response(query: str, search_type: str = "fio", count: int = 10, rng: Optional[random.Random] = None, reference_time: Optional[datetime] = None) -> Dict:
    """
    Fake response generation from Casebook API for testing
    
    Args:
        query: Search request (FIO, INN, name)
        search_type: Search type ("fio", "inn", "company")
        count: Number of results for generation
    
    Returns:
        A dictionary with response structure Casebook API
    """
    rng = rng or random
    reference_time = reference_time or datetime.now()

    courts = [
        'Court of Arbitration of Moscow',
        'Court of Arbitration of Moscow Region',
        'Court of Arbitration of St. Petersburg and Leningrad Region',
        'Court of Arbitration of the Moscow District',
        'Central District Court of Arbitration',
        'Court of Arbitration of the Northwest District',
        'Court of Arbitration of the Volj District',
        'Court of Arbitration of the Ural District',
        'Court of Arbitration of the Siberian District',
        'Far East District Court of Arbitration',
    ]
    
    regions = [
        'Moscow', 'Moscow Region', 'Saint Petersburg', 'Leningrad region',
        'Novosibir region', 'Catherineburg', 'Lower Novgorod', 'Kazan',
        'Krasnodar region', 'Perm Province'
    ]
    
    act_types = ['Decision', 'Definition', 'Regulation', 'Order']
    
    mention_types = ["истец", "ответчик", "участник", "контрагент", "третье лицо", 'Reference']

    q_variants = _query_variants(query, search_type)
    
    items = []
    
    for i in range(count):
        # Generate a random date in the last 3 years
        days_ago = rng.randint(0, 1095)
        case_date = (reference_time - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        
        # Generate case number.
        case_number = f"A{rng.randint(40, 75)}-{rng.randint(10000, 99999)}/{2021 + rng.randint(0, 3)}"
        
        court = rng.choice(courts)
        region = rng.choice(regions)
        act_type = rng.choice(act_types)
        mention_type = rng.choice(mention_types)

        qv1 = rng.choice(q_variants)
        qv2 = rng.choice(q_variants)
        qv3 = rng.choice(q_variants)
        
        # Generate context depending on the type of reference
        if mention_type == "истец":
            context_text = f"It has been established that {qv1} filed a claim with the court for the amount of the debt {rng.randint(100000, 5000000)} It's a ruble. In support of claims {qv2} referred to correspondence and the act of reconciliation. The Court granted the claims in part."
            parties = [f"Claimant: {qv1}", f"Defendant: OS & Company {rng.randint(1, 300)}'"]
        elif mention_type == "ответчик":
            context_text = f"The Court heard the case against the {qv1} on the recovery of contractual debts. {qv2} did not accept the claim, indicated the lack of delivery and stated the credit. In the text of the act {qv3} is mentioned repeatedly."
            parties = [f"Claimant: OS & Company {rng.randint(1, 300)}'", f"Defendant: {qv1}"]
        elif mention_type == "участник":
            context_text = f"He's involved in the case. {qv1} as a third person. {qv2} presented explanations, pointed out the affiliation of the parties and declared independent claims regarding the subject of the dispute."
            parties = [
                f"Claimant: OS & Company {rng.randint(1, 300)}'",
                f"Defendant: OS & Company {rng.randint(301, 600)}'",
                f"Third person: {qv1}"
            ]
        elif mention_type == "контрагент":
            context_text = f"The case file contains a contract concluded between the defendant and {qv1}. {qv2} is specified in the contract as a counterparty. Also found in the annexes to the treaty {qv3}."
            parties = [
                f"Claimant: OS & Company {rng.randint(1, 300)}'",
                f"Defendant: OS & Company {rng.randint(301, 600)}'"
            ]
        else:
            context_text = f"The text of the judicial act refers to {qv1}. Information on {qv2} in case files, correspondence and annexes. Additional {qv3}but the person was not involved."
            parties = [
                f"Claimant: OS & Company {rng.randint(1, 300)}'",
                f"Defendant: OS & Company {rng.randint(301, 600)}'"
            ]
        
        # Full text of the act (abbreviated)
        # Add multiple references to the noises to check: BM25, embeddings, lighting, grandpa.
        mentions_count = rng.randint(1, 12)
        mention_line = " ".join([rng.choice(q_variants) for _ in range(min(mentions_count, 6))])
        act_text = f"""
{act_type.upper()}

{case_number}

{court}

{case_date}

{context_text}

As a result of the proceedings, the Court found the following circumstances. 
The case file contains documents supporting the facts as set out in the statement of claim.
Reference (control): {mention_line}.
For full-text search: party/participant/contractor/memorandum.
The Court considers it necessary to satisfy the plaintiff &apos; s claims.

DECIDED:
Retrieve the defendant in favour of the plaintiff {rng.randint(100000, 5000000)} It's a ruble.
""".strip()
        
        public_base = os.getenv("PUBLIC_ACT_BASE_URL", "http://localhost:8000/api/acts")
        act_id = f"{case_number.replace('/', '-')}-{i+1}"

        item = {
            "case_number": case_number,
            "court_name": court,
            "date": case_date,
            # In the urine mode, we're going to point the URL to our gateway so it works to "slip the act" and "slip all the files."".
            "url": f"{public_base}/{act_id}/download",
            "parties": parties,
            "text": act_text,
            "content": act_text,
            "act_type": act_type,
            "type": act_type,
            "context": context_text,
            "type_of_mention": mention_type,
            "region": region,
            "category": 'Civil affairs',
            "mentions_count": mentions_count,  # Number of references in text
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
    Advanced Fake Data for Integrated Testing
    Including different scripts of references
    """
    # Scaling the wet data to show the ranking/lighting/LLM-topN for sure.
    # Determinated from (query, search_type) — that tests be repeated.
    seed = _stable_seed(query, search_type)
    rng = random.Random(seed)

    items: List[Dict] = []
    
    # Scenario 1: The plaintiff
    items.append({
        "case_number": 'A40-12345/2024',
        "court_name": 'Court of Arbitration of Moscow',
        "date": "2024-01-15",
        "url": "https://casebook.ru/cases/A40-12345-2024",
        "parties": [f"Claimant: {query}", 'Defendant: "Example Company"'],
        "text": f"{query} filed a claim for payment of debt under the contract of delivery. {query} submitted evidence. The Court granted the claims in part.",
        "content": f"{query} filed a claim for payment of debt under the contract of delivery. {query} submitted evidence. The Court granted the claims in part.",
        "act_type": 'Decision',
        "type": 'Decision',
        "context": f"The court hearing found that {query} I filed a lawsuit with the court.",
        "type_of_mention": "истец",
        "region": 'Moscow',
        "category": 'Civil affairs',
        "mentions_count": 3,
    })
    
    # Scenario 2: Respondent
    items.append({
        "case_number": 'A41-67890/2024',
        "court_name": 'Court of Arbitration of Moscow Region',
        "date": "2024-02-20",
        "url": "https://casebook.ru/cases/A41-67890-2024",
        "parties": ['Claimant: "Other Company"', f"Defendant: {query}"],
        "text": f"The Court heard the case against the {query} on the recovery of arrears. {query} I didn't accept the demands.",
        "content": f"The Court heard the case against the {query} on the recovery of arrears. {query} I didn't accept the demands.",
        "act_type": 'Decision',
        "type": 'Decision',
        "context": f"K {query} A claim for recovery of debts has been filed.",
        "type_of_mention": "ответчик",
        "region": 'Moscow Region',
        "category": 'Civil affairs',
        "mentions_count": 5,
    })
    
    # Scenario 3: Participant (third person)
    items.append({
        "case_number": 'A50-11111/2023',
        "court_name": 'Court of Arbitration of the Perm Region',
        "date": "2023-12-10",
        "url": "https://casebook.ru/cases/A50-11111-2023",
        "parties": [
            'Claimant: IP Ivanov I.I.',
            'Respondent: Third Company',
            f"Third person: {query}"
        ],
        "text": f"Participates in the case {query} as a third person. {query} I made a stand-alone claim.",
        "content": f"Participates in the case {query} as a third person. {query} I made a stand-alone claim.",
        "act_type": 'Definition',
        "type": 'Definition',
        "context": f"{query} In the case in question, he was tried as a third party.",
        "type_of_mention": "участник",
        "region": 'Perm Province',
        "category": 'Civil affairs',
        "mentions_count": 2,
    })
    
    # Scenario 4: Contractor (Remark in contract)
    items.append({
        "case_number": 'A43-2222/2024',
        "court_name": 'Court of Arbitration of St. Petersburg and Leningrad Region',
        "date": "2024-03-05",
        "url": "https://casebook.ru/cases/A43-22222-2024",
        "parties": ['The plaintiff: "A Company A"', 'Defendant: Company B'],
        "text": f"The case file contains a contract concluded between the defendant and {query}. {query} is specified in the contract as a counterparty.",
        "content": f"The case file contains a contract concluded between the defendant and {query}. {query} is specified in the contract as a counterparty.",
        "act_type": 'Decision',
        "type": 'Decision',
        "context": f"{query} is a counterparty to a contract concluded between the parties to the dispute.",
        "type_of_mention": "контрагент",
        "region": 'Saint Petersburg',
        "category": 'Civil affairs',
        "mentions_count": 4,
    })
    
    # Scenario 5: Simple mention (non-participant)
    items.append({
        "case_number": 'A55-33333/2023',
        "court_name": 'Court of Arbitration of Sverdlovsk Region',
        "date": "2023-11-18",
        "url": "https://casebook.ru/cases/A55-33333-2023",
        "parties": ['Claimant: Company B', 'Defendant: "G Company"'],
        "text": f"The text of the judicial act refers to {query}. {query} is in correspondence between the parties but is not a party to the case.",
        "content": f"The text of the judicial act refers to {query}. {query} is in correspondence between the parties but is not a party to the case.",
        "act_type": 'Definition',
        "type": 'Definition',
        "context": f"{query} referred to in the case file but not party to the dispute.",
        "type_of_mention": 'Reference',
        "region": 'Sverdlov region',
        "category": 'Civil affairs',
        "mentions_count": 2,
    })

    # Generate mass of additional data
    base_count = int(os.getenv("MOCK_RESULTS_COUNT", "80"))
    base_count = max(20, min(base_count, 250))

    generated = generate_mock_casebook_response(query=query, search_type=search_type, count=base_count, rng=rng)
    items.extend(generated.get("items", []))

    # Add a few acts to one case (to see a group/dup of URL, not a case number))
    if items:
        for k in range(3):
            src = rng.choice(items)
            clone = dict(src)
            clone["act_type"] = rng.choice(['Definition', 'Regulation', 'Decision'])
            clone["type"] = clone["act_type"]
            clone["date"] = (datetime.now() - timedelta(days=rng.randint(0, 600))).strftime("%Y-%m-%d")
            clone["url"] = f"{src.get('url','')}/followup-{k+1}"
            clone["context"] = f"Additional action in the case {clone.get('case_number','')}: {clone.get('context','')}"
            clone["mentions_count"] = int(src.get("mentions_count", 1)) + rng.randint(0, 3)
            items.append(clone)

    # Control duplicate URL (Check of deduplication))
    if len(items) >= 5:
        dupe_src = items[1]
        dupe = dict(dupe_src)
        dupe["mentions_count"] = int(dupe.get("mentions_count", 1)) + 1
        dupe["context"] = f"{dupe.get('context','')} (duplicate to verify deduplication)"
        # the same url = must be grandpa
        items.append(dupe)

    # Normalize limit/total
    return {
        "items": items,
        "total": len(items),
        "limit": len(items),
        "offset": 0
    }
