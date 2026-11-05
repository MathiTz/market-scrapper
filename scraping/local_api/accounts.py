"""Accounts for the local Flask API - the development mirror of api/src/accounts.ts.

Same routes, same request/response shapes, same messages: the UI cannot tell which backend it is
talking to. Passwords are PBKDF2-SHA-256 and sessions keep only a token hash, like the Worker.

Google sign-in needs GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET (and, in local development, set
ACCOUNTS_PUBLIC_URL to the UI's origin - http://127.0.0.1:3000 - so the callback lands on the page
that started the flow instead of on the API port).
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

import requests
from flask import jsonify, redirect, request
from sqlalchemy.exc import IntegrityError

from models.database import SessionLocal
from models.user import SavedList, User, UserPreference, UserSession

SESSION_COOKIE = "med_session"
OAUTH_COOKIE = "med_oauth_state"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 210_000
MIN_PASSWORD = 8
MAX_PASSWORD = 200
MAX_EMAIL = 254
MAX_NAME = 80
MAX_LIST_NAME = 80
MAX_LISTS = 20
MAX_LINES = 200
MAX_QUANTITY = 999
DEFAULT_REGION = "Fortaleza"

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


# ---------------------------------------------------------------------------------------------
# Validation (mirrors api/src/accounts.ts so a form behaves the same on both backends)
# ---------------------------------------------------------------------------------------------


def _normalize_email(raw) -> str:
    return raw.strip().lower() if isinstance(raw, str) else ""


def _email_problem(email: str):
    if not email:
        return "Informe um e-mail."
    if len(email) > MAX_EMAIL:
        return "O e-mail pode ter no máximo 254 caracteres."
    if not EMAIL.match(email):
        return "Digite um e-mail válido, como nome@exemplo.com."
    return None


def _password_problem(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres."
    if len(password) > MAX_PASSWORD:
        return f"A senha pode ter no máximo {MAX_PASSWORD} caracteres."
    return None


def _clean_name(raw):
    """The name, None when empty, or the sentinel ``False`` when it is too long."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not name:
        return None
    return name if len(name) <= MAX_NAME else False


def _clean_list_name(raw):
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    return name if name and len(name) <= MAX_LIST_NAME else None


def _sanitize_lines(raw):
    if not isinstance(raw, list) or len(raw) > MAX_LINES:
        return None
    lines = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        product_id = item.get("product_id")
        quantity = item.get("quantity")
        if not isinstance(product_id, str) or not product_id or len(product_id) > 200:
            return None
        if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= MAX_QUANTITY:
            return None
        name = item.get("name")
        lines.append(
            {
                "product_id": product_id,
                "name": name.strip()[:200] if isinstance(name, str) and name.strip() else "Item salvo",
                "quantity": quantity,
                "checked": item.get("checked") is True,
            }
        )
    return lines


def _sanitize_preferences(raw):
    if not isinstance(raw, dict):
        return None
    region = raw.get("region")
    region = region.strip() if isinstance(region, str) and region.strip() else DEFAULT_REGION
    if len(region) > MAX_NAME:
        return None
    location = raw.get("location")
    if location is None:
        return {"region": region, "location": None}
    if not isinstance(location, dict):
        return None
    label = location.get("label")
    label = label.strip() if isinstance(label, str) else ""
    latitude, longitude, radius = location.get("latitude"), location.get("longitude"), location.get("radius_km")
    valid = (
        0 < len(label) <= 200
        and isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and abs(latitude) <= 90
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and abs(longitude) <= 180
        and isinstance(radius, int)
        and not isinstance(radius, bool)
        and 1 <= radius <= 50
    )
    if not valid:
        return None
    return {
        "region": region,
        "location": {
            "label": label,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "radius_km": radius,
        },
    }


# ---------------------------------------------------------------------------------------------
# Passwords and sessions
# ---------------------------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, dklen=32)
    return "pbkdf2-sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored) -> bool:
    if not stored:
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2-sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        expected = base64.b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    if not 1 <= iterations <= 1_000_000:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, dklen=len(expected))
    return hmac.compare_digest(actual, expected)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    # Naive UTC, which is what SQLite stores and what the model columns hold.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value) -> str:
    return value.replace(tzinfo=None).isoformat() + "Z"


def _current_user(db):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    row = db.get(UserSession, _hash_token(token))
    if row is None:
        return None
    if row.expires_at <= _now():
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def _start_session(response, db, user):
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            token_hash=_hash_token(token),
            user_id=user.id,
            created_at=_now(),
            expires_at=_now() + timedelta(days=SESSION_DAYS),
        )
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 86_400,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
        path="/",
    )
    return response


def _same_origin() -> bool:
    """Refuse a state-changing request made by another site.

    The public origin and ACCOUNTS_PUBLIC_URL are the allowed ones. In local development the UI is on
    :3000 and this API on :5050 (Vite's proxy forwards the request, so the Origin no longer matches the
    Host), so loopback origins on the same host are accepted regardless of port.
    """
    origin = request.headers.get("Origin")
    if not origin:
        return True
    try:
        given = urlsplit(origin)
        here = urlsplit(request.host_url)
        allowed = {(here.scheme, here.netloc)}
        public = os.getenv("ACCOUNTS_PUBLIC_URL")
        if public:
            parts = urlsplit(public)
            allowed.add((parts.scheme, parts.netloc))
        if (given.scheme, given.netloc) in allowed:
            return True
        return given.hostname in ("127.0.0.1", "localhost", "::1") and given.hostname == here.hostname
    except ValueError:
        return False


# ---------------------------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------------------------


def _user_json(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "created_at": _iso(user.created_at or _now()),
    }


def _preferences_json(db, user_id: str) -> dict:
    row = db.get(UserPreference, user_id)
    if row is None:
        return {"region": DEFAULT_REGION, "location": None}
    location = (
        {
            "label": row.location_label,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "radius_km": row.radius_km,
        }
        if row.location_label and row.latitude is not None and row.longitude is not None and row.radius_km is not None
        else None
    )
    return {"region": row.region, "location": location}


def _list_json(row: SavedList) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "lines": row.lines or [],
        "created_at": _iso(row.created_at or _now()),
        "updated_at": _iso(row.updated_at or row.created_at or _now()),
    }


def _require_user(db):
    user = _current_user(db)
    if user is None:
        return None, (jsonify({"error": "Entre na sua conta para continuar."}), 401)
    return user, None


# ---------------------------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------------------------


def _decode_claims(id_token: str):
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return None


def _public_base() -> str:
    return (os.getenv("ACCOUNTS_PUBLIC_URL") or request.host_url).rstrip("/")


def _conta_redirect(query: str, clear_state: bool = True):
    response = redirect(f"{_public_base()}/conta?{query}")
    if clear_state:
        response.delete_cookie(OAUTH_COOKIE, path="/api/auth/google")
    return response


# ---------------------------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------------------------


def register_account_routes(app):
    """Attach the account routes to the Flask app (api/src/accounts.ts is the production twin)."""

    @app.after_request
    def _account_headers(response):
        # Account answers are per-person: no browser, proxy or cache may keep a copy.
        if request.path.startswith(("/api/auth/", "/api/account/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/auth/register")
    def api_register():
        if not _same_origin():
            return jsonify({"error": "Origem inválida."}), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Envie os dados em JSON."}), 400
        email = _normalize_email(body.get("email"))
        problem = _email_problem(email) or _password_problem(body.get("password"))
        if problem:
            return jsonify({"error": problem}), 400
        name = _clean_name(body.get("name"))
        if name is False:
            return jsonify({"error": f"O nome pode ter no máximo {MAX_NAME} caracteres."}), 400

        db = SessionLocal()
        try:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=hash_password(body["password"]),
                name=name,
                google_sub=None,
                created_at=_now(),
            )
            db.add(user)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return jsonify({"error": "Já existe uma conta com este e-mail. Entre com sua senha."}), 409
            response = jsonify(
                {"user": _user_json(user), "preferences": {"region": DEFAULT_REGION, "location": None}}
            )
            response.status_code = 201
            return _start_session(response, db, user)
        finally:
            db.close()

    @app.post("/api/auth/login")
    def api_login():
        if not _same_origin():
            return jsonify({"error": "Origem inválida."}), 403
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        email = _normalize_email(body.get("email"))
        password = body.get("password") if isinstance(body.get("password"), str) else ""
        if not email or not password:
            return jsonify({"error": "Informe o e-mail e a senha."}), 400

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).one_or_none()
            # The same answer for an unknown e-mail and a wrong password: nothing to enumerate.
            if user is None or not verify_password(password, user.password_hash):
                return jsonify({"error": "E-mail ou senha incorretos."}), 401
            return _start_session(
                jsonify({"user": _user_json(user), "preferences": _preferences_json(db, user.id)}),
                db,
                user,
            )
        finally:
            db.close()

    @app.post("/api/auth/logout")
    def api_logout():
        if not _same_origin():
            return jsonify({"error": "Origem inválida."}), 403
        db = SessionLocal()
        try:
            token = request.cookies.get(SESSION_COOKIE)
            if token:
                row = db.get(UserSession, _hash_token(token))
                if row is not None:
                    db.delete(row)
                    db.commit()
        finally:
            db.close()
        response = jsonify({"ok": True})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/auth/me")
    def api_me():
        db = SessionLocal()
        try:
            user = _current_user(db)
            return jsonify(
                {
                    "user": _user_json(user) if user else None,
                    "preferences": _preferences_json(db, user.id) if user else None,
                    "google": bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")),
                }
            )
        finally:
            db.close()

    @app.get("/api/auth/google/start")
    def api_google_start():
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if not client_id or not client_secret:
            return jsonify({"error": "Entrar com Google não está configurado neste servidor."}), 503
        state = secrets.token_urlsafe(24)
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": f"{_public_base()}/api/auth/google/callback",
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )
        response = redirect(url)
        response.set_cookie(
            OAUTH_COOKIE,
            state,
            max_age=600,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure,
            path="/api/auth/google",
        )
        return response

    @app.get("/api/auth/google/callback")
    def api_google_callback():
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        state = request.args.get("state") or ""
        expected = request.cookies.get(OAUTH_COOKIE) or ""
        if not client_id or not client_secret:
            return _conta_redirect("erro=google-indisponivel")
        if not state or not expected or not hmac.compare_digest(state, expected):
            return _conta_redirect("erro=google-estado")
        code = request.args.get("code")
        if not code:
            return _conta_redirect("erro=google-cancelado")

        try:
            exchange = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": f"{_public_base()}/api/auth/google/callback",
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            if not exchange.ok:
                return _conta_redirect("erro=google-token")
            claims = _decode_claims((exchange.json() or {}).get("id_token") or "")
        except (requests.RequestException, ValueError):
            return _conta_redirect("erro=google-token")

        # The token came straight from Google over TLS, so its claims are trusted once they match this app.
        issuer = claims.get("iss") if isinstance(claims, dict) else None
        audience = claims.get("aud") if isinstance(claims, dict) else None
        expires = claims.get("exp") if isinstance(claims, dict) else None
        sub = claims.get("sub") if isinstance(claims, dict) else None
        email = _normalize_email(claims.get("email") if isinstance(claims, dict) else None)
        verified = isinstance(claims, dict) and claims.get("email_verified") in (True, "true")
        if (
            issuer not in ("accounts.google.com", "https://accounts.google.com")
            or audience != client_id
            or not isinstance(expires, (int, float))
            or expires <= time.time()
            or not isinstance(sub, str)
            or not sub
            or _email_problem(email)
            or not verified
        ):
            return _conta_redirect("erro=google-token")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.google_sub == sub).one_or_none()
            if user is None:
                existing = db.query(User).filter(User.email == email).one_or_none()
                if existing is not None:
                    existing.google_sub = sub
                    db.commit()
                    user = existing
                else:
                    user = User(
                        id=str(uuid.uuid4()),
                        email=email,
                        password_hash=None,
                        name=_clean_name(claims.get("name")) or None,
                        google_sub=sub,
                        created_at=_now(),
                    )
                    db.add(user)
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        user = db.query(User).filter(User.email == email).one_or_none()
                        if user is None:
                            return _conta_redirect("erro=google-conta")
                        user.google_sub = sub
                        db.commit()
            response = _conta_redirect("entrou=google")
            return _start_session(response, db, user)
        finally:
            db.close()

    @app.get("/api/account/preferences")
    def api_preferences():
        db = SessionLocal()
        try:
            user, error = _require_user(db)
            if error:
                return error
            return jsonify({"preferences": _preferences_json(db, user.id)})
        finally:
            db.close()

    @app.put("/api/account/preferences")
    def api_save_preferences():
        if not _same_origin():
            return jsonify({"error": "Origem inválida."}), 403
        db = SessionLocal()
        try:
            user, error = _require_user(db)
            if error:
                return error
            preferences = _sanitize_preferences(request.get_json(silent=True))
            if preferences is None:
                return jsonify({"error": "Preferências inválidas."}), 400
            row = db.get(UserPreference, user.id)
            if row is None:
                row = UserPreference(user_id=user.id, region=preferences["region"], updated_at=_now())
                db.add(row)
            place = preferences["location"]
            row.region = preferences["region"]
            row.location_label = place["label"] if place else None
            row.latitude = place["latitude"] if place else None
            row.longitude = place["longitude"] if place else None
            row.radius_km = place["radius_km"] if place else None
            row.updated_at = _now()
            db.commit()
            return jsonify({"preferences": _preferences_json(db, user.id)})
        finally:
            db.close()

    @app.get("/api/account/lists")
    def api_lists():
        db = SessionLocal()
        try:
            user, error = _require_user(db)
            if error:
                return error
            rows = (
                db.query(SavedList)
                .filter(SavedList.user_id == user.id)
                .order_by(SavedList.updated_at.desc())
                .all()
            )
            return jsonify({"lists": [_list_json(row) for row in rows]})
        finally:
            db.close()

    @app.post("/api/account/lists")
    def api_create_list():
        if not _same_origin():
            return jsonify({"error": "Origem inválida."}), 403
        db = SessionLocal()
        try:
            user, error = _require_user(db)
            if error:
                return error
            body = request.get_json(silent=True)
            body = body if isinstance(body, dict) else {}
            name = _clean_list_name(body.get("name"))
            lines = _sanitize_lines(body.get("lines"))
            if not name:
                return jsonify({"error": f"Dê um nome à lista (até {MAX_LIST_NAME} caracteres)."}), 400
            if lines is None:
                return jsonify({"error": "A lista enviada é inválida."}), 400
            count = db.query(SavedList).filter(SavedList.user_id == user.id).count()
            if count >= MAX_LISTS:
                return jsonify({"error": f"Você já tem {MAX_LISTS} listas salvas. Exclua uma para salvar outra."}), 409
            now = _now()
            row = SavedList(
                id=str(uuid.uuid4()),
                user_id=user.id,
                name=name,
                lines=lines,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.commit()
            return jsonify({"list": _list_json(row)}), 201
        finally:
            db.close()

    @app.put("/api/account/lists/<list_id>")
    def api_update_list(list_id):
        if not _same_origin():
            return jsonify({"error": "Origem inválida."}), 403
        db = SessionLocal()
        try:
            user, error = _require_user(db)
            if error:
                return error
            body = request.get_json(silent=True)
            body = body if isinstance(body, dict) else {}
            name = _clean_list_name(body.get("name"))
            lines = _sanitize_lines(body.get("lines"))
            if not name:
                return jsonify({"error": f"Dê um nome à lista (até {MAX_LIST_NAME} caracteres)."}), 400
            if lines is None:
                return jsonify({"error": "A lista enviada é inválida."}), 400
            row = (
                db.query(SavedList)
                .filter(SavedList.id == list_id, SavedList.user_id == user.id)
                .one_or_none()
            )
            if row is None:
                return jsonify({"error": "Lista não encontrada."}), 404
            row.name = name
            row.lines = lines
            row.updated_at = _now()
            db.commit()
            return jsonify({"list": _list_json(row)})
        finally:
            db.close()

    @app.delete("/api/account/lists/<list_id>")
    def api_delete_list(list_id):
        if not _same_origin():
            return jsonify({"error": "Origem inválida."}), 403
        db = SessionLocal()
        try:
            user, error = _require_user(db)
            if error:
                return error
            row = (
                db.query(SavedList)
                .filter(SavedList.id == list_id, SavedList.user_id == user.id)
                .one_or_none()
            )
            if row is None:
                return jsonify({"error": "Lista não encontrada."}), 404
            db.delete(row)
            db.commit()
            return jsonify({"ok": True})
        finally:
            db.close()
