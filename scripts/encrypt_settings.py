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


def encrypt_settings(plain: dict, passphrase: str, iterations: int) -> dict:
    from cryptography.fernet import Fernet

    salt = os.urandom(16)
    key = derive_key(passphrase, salt, iterations)
    f = Fernet(key)
    token = f.encrypt(json.dumps(plain, ensure_ascii=False).encode("utf-8"))
    return {
        "v": 1,
        "kdf": "pbkdf2-sha256",
        "iter": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "token": base64.b64encode(token).decode("ascii"),
    }


def main():
    p = argparse.ArgumentParser(description="Encrypt settings.json into settings.json.enc (Fernet + PBKDF2).")
    p.add_argument("--in", dest="in_path", required=True, help="Path to plaintext settings.json")
    p.add_argument("--out", dest="out_path", required=True, help="Path to write settings.json.enc")
    p.add_argument("--passphrase", required=False, help="Encryption passphrase (or use SETTINGS_PASSPHRASE env)")
    p.add_argument("--iterations", type=int, default=200000, help="PBKDF2 iterations (default: 200000)")
    args = p.parse_args()

    passphrase = args.passphrase or os.getenv("SETTINGS_PASSPHRASE") or ""
    if not passphrase:
        raise SystemExit("Passphrase is required. Provide --passphrase or set SETTINGS_PASSPHRASE.")

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)

    # On Windows PowerShell sometimes writes JSON with BOM ♪ Read as utf-8-sig
    plain = json.loads(in_path.read_text(encoding="utf-8-sig"))
    enc = encrypt_settings(plain, passphrase, args.iterations)
    out_path.write_text(json.dumps(enc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: encrypted -> {out_path}")


if __name__ == "__main__":
    main()

