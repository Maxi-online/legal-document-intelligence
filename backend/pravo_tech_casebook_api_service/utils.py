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
    'Loading settings from settings.json'
    # First check in the current directory (for Docker containers))
    current_file = Path(__file__)
    # In the Docker container, the file can be in /app/
    possible_plain_paths = [
        current_file.parent / "settings.json",  # Near utils.py
        Path("/app/settings.json"),  # In the root of the app directory (Docker)
        current_file.parent.parent / "settings.json",  # At the root of the project (local)
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
        raise FileNotFoundError(f"settings.json(.enc) file not found. Roads tested: {possible_enc_paths + possible_plain_paths}")

    with open(settings_path, "r", encoding="utf-8-sig") as f:
        return _resolve_settings_env(json.load(f))

def get_openai_api_key():
    'Receive OpenAI API key from settings.json'
    settings = load_settings()
    return settings.get("openai", {}).get("api_key", "")

def get_casebook_api_key():
    'Collection of settings.json Key Casebook API)'
    env_key = os.getenv("CASEBOOK_API_KEY") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_API_KEY")
    if env_key:
        return env_key
    settings = load_settings()
    return settings.get("casebook", {}).get("api_key", "")

def get_casebook_username():
    'Get Logic for Casebook API from settings.json'
    env_username = os.getenv("CASEBOOK_USERNAME") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_USERNAME")
    if env_username:
        return env_username
    settings = load_settings()
    return settings.get("casebook", {}).get("username", "")

def get_casebook_password():
    'Obtain password for Casebook API from settings.json'
    env_password = os.getenv("CASEBOOK_PASSWORD") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_PASSWORD")
    if env_password:
        return env_password
    settings = load_settings()
    return settings.get("casebook", {}).get("password", "")

def get_casebook_base_url():
    'Receive Casebook API basic URL from settings.json'
    env_url = os.getenv("CASEBOOK_BASE_URL") or os.getenv("DOCUMENT_INTELLIGENCE_CASEBOOK_BASE_URL")
    if env_url:
        return env_url
    settings = load_settings()
    return settings.get("casebook", {}).get("base_url", "https://api3.casebook.ru")

