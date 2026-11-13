import argparse
import json
import secrets
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description="Add/update an auth user in settings.json (bcrypt) and ensure auth.jwt.secret exists.")
    p.add_argument("--settings", required=True, help="Path to plaintext settings.json (will be updated in-place)")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--ttl-minutes", type=int, default=60)
    p.add_argument("--jwt-secret", default="", help="Optional. If empty, a random secret will be generated.")
    p.add_argument("--roles", default="", help="Comma-separated roles (e.g. admin,user). If empty: admin->admin else user.")
    args = p.parse_args()

    settings_path = Path(args.settings)
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    auth = settings.get("auth") or {}
    jwt_cfg = auth.get("jwt") or {}
    users = auth.get("users") or []

    jwt_secret = args.jwt_secret or jwt_cfg.get("secret") or secrets.token_urlsafe(48)
    jwt_cfg["secret"] = jwt_secret
    jwt_cfg["access_token_ttl_minutes"] = int(args.ttl_minutes)

    import bcrypt
    password_bcrypt = bcrypt.hashpw(args.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    roles = []
    if args.roles.strip():
        roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    else:
        roles = ["admin"] if args.username == "admin" else ["user"]

    # upsert user
    updated = False
    for u in users:
        if isinstance(u, dict) and u.get("username") == args.username:
            u["password_bcrypt"] = password_bcrypt
            u["roles"] = roles
            updated = True
            break

    if not updated:
        users.append({"username": args.username, "password_bcrypt": password_bcrypt, "roles": roles})

    auth["jwt"] = jwt_cfg
    auth["users"] = users
    settings["auth"] = auth

    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: user '{args.username}' written to {settings_path}")
    print("NOTE: jwt secret set/kept in settings.auth.jwt.secret")


if __name__ == "__main__":
    main()

