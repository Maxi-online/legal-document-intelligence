import json
import os
from pathlib import Path
from typing import Dict, Any
import base64


def _resolve_settings_env(value):
    """Resolve required environment references in already parsed configuration."""
    import os
    import re
    if isinstance(value, dict):
        return {key: _resolve_settings_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_settings_env(item) for item in value]
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\$\{([A-Z_][A-Z0-9_]*)(?::(int|float|bool))?\}", value)
    if match is None:
        return value
    name, kind = match.groups()
    content = os.environ.get(name)
    if content is None or not content.strip():
        raise RuntimeError(f"Required configuration variable is missing: {name}")
    if kind == "int":
        return int(content)
    if kind == "float":
        return float(content)
    if kind == "bool":
        if content.lower() not in {"true", "false", "1", "0"}:
            raise ValueError(f"Expected a boolean configuration variable: {name}")
        return content.lower() in {"true", "1"}
    return content



def _decrypt_settings_payload(payload: Dict[str, Any], passphrase: str) -> Dict[str, Any]:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.fernet import Fernet

    v = int(payload.get("v", 0))
    if v != 1:
        raise ValueError("Unsupported settings encryption version")

    salt_b64 = payload.get("salt")
    token_b64 = payload.get("token")
    iters = int(payload.get("iter", 200000))
    if not salt_b64 or not token_b64:
        raise ValueError("Invalid encrypted settings payload (missing salt/token)")

    salt = base64.b64decode(salt_b64)
    token = base64.b64decode(token_b64)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iters,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    f = Fernet(key)
    plaintext = f.decrypt(token)
    return _resolve_settings_env(json.loads(plaintext.decode("utf-8")))

def load_settings():
    """Загрузка настроек из settings.json"""
    # Сначала проверяем в текущей директории (для Docker контейнеров)
    current_file = Path(__file__)
    # В Docker контейнере файл может быть в /app/
    possible_plain_paths = [
        current_file.parent / "settings.json",  # Рядом с utils.py
        Path("/app/settings.json"),  # В корне app директории (Docker)
        current_file.parent.parent / "settings.json",  # В корне проекта (локально)
        Path("/settings.json"),
    ]
    possible_enc_paths = [
        current_file.parent / "settings.json.enc",
        Path("/app/settings.json.enc"),
        current_file.parent.parent / "settings.json.enc",
        Path("/settings.json.enc"),
    ]
    
    settings_path = None

    for path in possible_enc_paths:
        if path.exists():
            settings_path = path
            break

    if settings_path and str(settings_path).endswith(".enc"):
        passphrase = os.getenv("SETTINGS_PASSPHRASE", "")
        if not passphrase:
            raise RuntimeError("SETTINGS_PASSPHRASE is required to decrypt settings.json.enc")
        with open(settings_path, "r", encoding="utf-8-sig") as f:
            payload = _resolve_settings_env(json.load(f))
        return _decrypt_settings_payload(payload, passphrase)

    for path in possible_plain_paths:
        if path.exists():
            settings_path = path
            break

    if not settings_path:
        raise FileNotFoundError(f"Файл settings.json(.enc) не найден. Проверенные пути: {possible_enc_paths + possible_plain_paths}")

    with open(settings_path, "r", encoding="utf-8-sig") as f:
        return _resolve_settings_env(json.load(f))

def get_openai_api_key():
    """Получение OpenAI API ключа из settings.json"""
    settings = load_settings()
    return settings.get("openai", {}).get("api_key", "")

def get_casebook_api_key():
    """Получение Casebook API ключа из settings.json (устаревший метод, для обратной совместимости)"""
    env_key = os.getenv("CASEBOOK_API_KEY") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_API_KEY")
    if env_key:
        return env_key
    settings = load_settings()
    return settings.get("casebook", {}).get("api_key", "")

def get_casebook_username():
    """Получение логина для Casebook API из settings.json"""
    env_username = os.getenv("CASEBOOK_USERNAME") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_USERNAME")
    if env_username:
        return env_username
    settings = load_settings()
    return settings.get("casebook", {}).get("username", "")

def get_casebook_password():
    """Получение пароля для Casebook API из settings.json"""
    env_password = os.getenv("CASEBOOK_PASSWORD") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_PASSWORD")
    if env_password:
        return env_password
    settings = load_settings()
    return settings.get("casebook", {}).get("password", "")

def get_casebook_base_url():
    """Получение Casebook API базового URL из settings.json"""
    env_url = os.getenv("CASEBOOK_BASE_URL") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_BASE_URL")
    if env_url:
        return env_url
    settings = load_settings()
    return settings.get("casebook", {}).get("base_url", "https://api3.casebook.ru")

