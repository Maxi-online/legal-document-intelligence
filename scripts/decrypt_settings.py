import argparse
import base64
import json
import os
from pathlib import Path


def derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def decrypt_payload(payload: dict, passphrase: str) -> dict:
    from cryptography.fernet import Fernet

    if int(payload.get("v", 0)) != 1:
        raise ValueError("Unsupported settings encryption version")
    salt = base64.b64decode(payload["salt"])
    token = base64.b64decode(payload["token"])
    iters = int(payload.get("iter", 200000))

    key = derive_key(passphrase, salt, iters)
    f = Fernet(key)
    plaintext = f.decrypt(token)
    return json.loads(plaintext.decode("utf-8"))


def main():
    p = argparse.ArgumentParser(description="Decrypt settings.json.enc into settings.json")
    p.add_argument("--in", dest="in_path", required=True, help="Path to settings.json.enc")
    p.add_argument("--out", dest="out_path", required=True, help="Path to write plaintext settings.json")
    p.add_argument("--passphrase", required=False, help="Decryption passphrase (or use SETTINGS_PASSPHRASE env)")
    args = p.parse_args()

    passphrase = args.passphrase or os.getenv("SETTINGS_PASSPHRASE") or ""
    if not passphrase:
        raise SystemExit("Passphrase is required. Provide --passphrase or set SETTINGS_PASSPHRASE.")

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)

    payload = json.loads(in_path.read_text(encoding="utf-8-sig"))
    plain = decrypt_payload(payload, passphrase)
    out_path.write_text(json.dumps(plain, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: decrypted -> {out_path}")


if __name__ == "__main__":
    main()

