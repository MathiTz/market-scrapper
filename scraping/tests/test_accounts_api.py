"""Tests for the account routes of the local Flask API (the mirror of api/src/accounts.ts)."""

import base64
import json
import os
import time
import unittest
from unittest.mock import patch

# Must be set before local_api.app imports config: never touch the real market.db.
os.environ["DATABASE_URL"] = "sqlite://"

from local_api.accounts import hash_password, verify_password  # noqa: E402
from local_api.app import app  # noqa: E402
from models.database import SessionLocal  # noqa: E402
from models.user import SavedList, User, UserPreference, UserSession  # noqa: E402


def _id_token(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims, ensure_ascii=False).encode("utf-8")).decode().rstrip("=")
    return f"header.{payload}.signature"


class FakeGoogleResponse:
    def __init__(self, payload):
        self._payload = payload
        self.ok = True

    def json(self):
        return self._payload


class TestAccountsApi(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        db = SessionLocal()
        try:
            for model in (SavedList, UserPreference, UserSession, User):
                db.query(model).delete()
            db.commit()
        finally:
            db.close()

    def register(self, email="ana@example.com", password="segredo123", name=None):
        body = {"email": email, "password": password}
        if name is not None:
            body["name"] = name
        return self.client.post("/api/auth/register", json=body)

    def login(self, email="ana@example.com", password="segredo123"):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def test_me_is_signed_out_before_any_account(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"user": None, "preferences": None, "google": False})
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_register_signs_in_with_normalised_email(self):
        response = self.register(" Ana@Example.com ", name="Ana")
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["user"]["email"], "ana@example.com")
        self.assertEqual(data["user"]["name"], "Ana")
        self.assertEqual(data["preferences"], {"region": "Fortaleza", "location": None})
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

        me = self.client.get("/api/auth/me").get_json()
        self.assertEqual(me["user"]["email"], "ana@example.com")
        self.assertEqual(me["preferences"], {"region": "Fortaleza", "location": None})

    def test_register_refuses_a_second_account_with_the_same_email(self):
        self.assertEqual(self.register().status_code, 201)
        again = self.register("ANA@example.com")
        self.assertEqual(again.status_code, 409)
        self.assertIn("Já existe uma conta", again.get_json()["error"])

    def test_register_validates_email_password_and_name(self):
        for body in (
            {"email": "sem-arroba", "password": "segredo123"},
            {"email": "ana@example.com", "password": "curta"},
            {"email": "ana@example.com"},
            {"email": "ana@example.com", "password": "segredo123", "name": "x" * 81},
        ):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/auth/register", json=body).status_code, 400)

    def test_login_and_logout(self):
        self.register()
        wrong = self.login(password="errada123")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.get_json()["error"], "E-mail ou senha incorretos.")

        unknown = self.login("ninguem@example.com")
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(unknown.get_json()["error"], "E-mail ou senha incorretos.")

        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertIsNone(self.client.get("/api/auth/me").get_json()["user"])

    def test_login_validates_email_and_password(self):
        for body in (
            {"email": "sem-arroba", "password": "segredo123"},
            {"email": "ana@example.com", "password": "curta"},
        ):
            with self.subTest(body=body):
                response = self.client.post("/api/auth/login", json=body)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())

    def test_login_throttling_and_reset(self):
        self.register("throttle@example.com", "segredo123")
        headers1 = {"CF-Connecting-IP": "203.0.113.50"}

        for _ in range(10):
            res = self.client.post(
                "/api/auth/login",
                json={"email": "throttle@example.com", "password": "errada123"},
                headers=headers1,
            )
            self.assertEqual(res.status_code, 401)
        res = self.client.post(
            "/api/auth/login",
            json={"email": "throttle@example.com", "password": "errada123"},
            headers=headers1,
        )
        self.assertEqual(res.status_code, 429)
        self.assertIn("Muitas tentativas", res.get_json()["error"])

        headers2 = {"CF-Connecting-IP": "203.0.113.60"}
        for _ in range(9):
            res = self.client.post(
                "/api/auth/login",
                json={"email": "throttle@example.com", "password": "errada123"},
                headers=headers2,
            )
            self.assertEqual(res.status_code, 401)
        res = self.client.post(
            "/api/auth/login",
            json={"email": "throttle@example.com", "password": "segredo123"},
            headers=headers2,
        )
        self.assertEqual(res.status_code, 200)
        for _ in range(9):
            res = self.client.post(
                "/api/auth/login",
                json={"email": "throttle@example.com", "password": "errada123"},
                headers=headers2,
            )
            self.assertEqual(res.status_code, 401)

    def test_state_changing_requests_refuse_another_origin(self):
        response = self.client.post(
            "/api/auth/register",
            json={"email": "ana@example.com", "password": "segredo123"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(response.status_code, 403)

    def test_accepts_the_ui_on_another_loopback_port(self):
        # The Vite proxy forwards the browser's Origin (the UI port) to this API's port.
        response = self.client.post(
            "/api/auth/register",
            json={"email": "ana@example.com", "password": "segredo123"},
            headers={"Origin": "http://127.0.0.1:3000"},
            base_url="http://127.0.0.1:5050",
        )
        self.assertEqual(response.status_code, 201)

    def test_accepts_the_configured_public_url(self):
        with patch.dict(os.environ, {"ACCOUNTS_PUBLIC_URL": "https://mercadoemdia.example"}):
            response = self.client.post(
                "/api/auth/register",
                json={"email": "ana@example.com", "password": "segredo123"},
                headers={"Origin": "https://mercadoemdia.example"},
            )
        self.assertEqual(response.status_code, 201)

    def test_preferences_need_a_session(self):
        self.assertEqual(self.client.get("/api/account/preferences").status_code, 401)

    def test_preferences_save_read_and_clear(self):
        self.register()
        location = {"label": "Casa · Rua A, 10 · Meireles", "latitude": -3.72, "longitude": -38.5, "radius_km": 5}
        saved = self.client.put("/api/account/preferences", json={"region": "Fortaleza", "location": location})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["preferences"], {"region": "Fortaleza", "location": location})
        self.assertEqual(self.client.get("/api/account/preferences").get_json()["preferences"]["location"], location)

        cleared = self.client.put("/api/account/preferences", json={"region": "Fortaleza", "location": None})
        self.assertEqual(cleared.get_json()["preferences"]["location"], None)

    def test_preferences_refuse_a_malformed_place(self):
        self.register()
        for location in (
            {"label": "", "latitude": -3.7, "longitude": -38.5, "radius_km": 5},
            {"label": "Casa", "latitude": 91, "longitude": -38.5, "radius_km": 5},
            {"label": "Casa", "latitude": -3.7, "longitude": -38.5, "radius_km": 2.5},
            {"label": "Casa", "latitude": -3.7, "longitude": -38.5, "radius_km": 80},
        ):
            with self.subTest(location=location):
                response = self.client.put("/api/account/preferences", json={"region": "Fortaleza", "location": location})
                self.assertEqual(response.status_code, 400)

    LINES = [
        {"product_id": "arroz-5kg", "name": "Arroz 5 kg", "quantity": 2, "checked": False},
        {"product_id": "feijao-1kg", "name": "Feijão 1 kg", "quantity": 1, "checked": True},
    ]

    def test_lists_belong_to_the_signed_in_account(self):
        self.register()
        created = self.client.post("/api/account/lists", json={"name": "Mercado da semana", "lines": self.LINES})
        self.assertEqual(created.status_code, 201)
        saved = created.get_json()["list"]
        self.assertEqual(saved["lines"], self.LINES)
        self.assertEqual(len(self.client.get("/api/account/lists").get_json()["lists"]), 1)

        self.client.post("/api/auth/logout")
        self.register("outra@example.com")
        self.assertEqual(self.client.get("/api/account/lists").get_json()["lists"], [])
        stolen = self.client.put(f"/api/account/lists/{saved['id']}", json={"name": "x", "lines": []})
        self.assertEqual(stolen.status_code, 404)

    def test_list_update_and_delete(self):
        self.register()
        created = self.client.post("/api/account/lists", json={"name": "Antiga", "lines": self.LINES})
        list_id = created.get_json()["list"]["id"]
        updated = self.client.put(f"/api/account/lists/{list_id}", json={"name": "Nova", "lines": []})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["list"]["name"], "Nova")
        self.assertEqual(updated.get_json()["list"]["lines"], [])

        self.assertEqual(self.client.delete(f"/api/account/lists/{list_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/account/lists").get_json()["lists"], [])
        self.assertEqual(self.client.delete(f"/api/account/lists/{list_id}").status_code, 404)

    def test_list_validation_and_limit(self):
        self.register()
        for body in (
            {"name": "", "lines": self.LINES},
            {"name": "x" * 81, "lines": self.LINES},
            {"name": "Lista", "lines": [{"product_id": "", "name": "x", "quantity": 1, "checked": False}]},
            {"name": "Lista", "lines": [{"product_id": "a", "name": "x", "quantity": 0, "checked": False}]},
            {"name": "Lista", "lines": [{"product_id": "a", "name": "x", "quantity": 1.5, "checked": False}]},
            {"name": "Lista", "lines": [{"product_id": "a", "name": "x", "quantity": 1, "checked": False}, 42]},
            {"name": "Lista", "lines": "não é lista"},
        ):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/account/lists", json=body).status_code, 400)

        for i in range(20):
            self.assertEqual(
                self.client.post("/api/account/lists", json={"name": f"Lista {i}", "lines": []}).status_code, 201
            )
        self.assertEqual(self.client.post("/api/account/lists", json={"name": "Uma a mais", "lines": []}).status_code, 409)

    def test_list_accepts_integral_float_quantity(self):
        self.register()
        lines = [{"product_id": "arroz-5kg", "name": "Arroz", "quantity": 1.0, "checked": False}]
        created = self.client.post("/api/account/lists", json={"name": "Lista Float", "lines": lines})
        self.assertEqual(created.status_code, 201)
        saved = created.get_json()["list"]
        self.assertEqual(saved["lines"][0]["quantity"], 1)
        self.assertIsInstance(saved["lines"][0]["quantity"], int)

    def test_google_says_so_when_unconfigured(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CLIENT_ID", None)
            os.environ.pop("GOOGLE_CLIENT_SECRET", None)
            self.assertEqual(self.client.get("/api/auth/google/start").status_code, 503)

    def test_google_start_and_mismatched_state(self):
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "client-id", "GOOGLE_CLIENT_SECRET": "secret"}):
            start = self.client.get("/api/auth/google/start")
            self.assertEqual(start.status_code, 302)
            self.assertIn("accounts.google.com", start.headers["Location"])
            mismatch = self.client.get("/api/auth/google/callback?code=abc&state=wrong")
            self.assertEqual(mismatch.status_code, 302)
            self.assertIn("/conta?erro=google-estado", mismatch.headers["Location"])

    def test_google_callback_rejects_non_ascii_state(self):
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "client-id", "GOOGLE_CLIENT_SECRET": "secret"}):
            self.client.set_cookie("med_oauth_state", "some-state", path="/api/auth/google")
            response = self.client.get("/api/auth/google/callback?state=%C3%A9")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/conta?erro=google-estado", response.headers["Location"])

            # A hostile cookie value must not reach hmac.compare_digest (it raises on non-ASCII).
            self.client.set_cookie("med_oauth_state", "é", path="/api/auth/google")
            response = self.client.get("/api/auth/google/callback?state=abc")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/conta?erro=google-estado", response.headers["Location"])

    def test_google_creates_an_account_and_signs_in(self):
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "client-id",
            "exp": int(time.time()) + 300,
            "sub": "google-sub-1",
            "email": "gmail@example.com",
            "email_verified": True,
            "name": "Gmail da Silva",
        }
        env = {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "secret",
            "ACCOUNTS_PUBLIC_URL": "http://localhost:3000",
        }
        with patch.dict(os.environ, env), patch(
            "local_api.accounts.requests.post", return_value=FakeGoogleResponse({"id_token": _id_token(claims)})
        ) as exchange:
            start = self.client.get("/api/auth/google/start")
            state = start.headers["Location"].split("state=")[1].split("&")[0]
            callback = self.client.get(f"/api/auth/google/callback?code=abc&state={state}")
            self.assertEqual(callback.status_code, 302)
            self.assertEqual(callback.headers["Location"], "http://localhost:3000/conta?entrou=google")
            me = self.client.get("/api/auth/me").get_json()
            self.assertEqual(me["user"]["email"], "gmail@example.com")
            self.assertEqual(me["user"]["name"], "Gmail da Silva")
            self.assertEqual(exchange.call_args.kwargs["data"]["grant_type"], "authorization_code")

    def test_google_non_ascii_name_saved_correctly(self):
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "client-id",
            "exp": int(time.time()) + 300,
            "sub": "google-sub-utf8",
            "email": "jose@example.com",
            "email_verified": True,
            "name": "José Conceição",
        }
        env = {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "secret",
            "ACCOUNTS_PUBLIC_URL": "http://localhost:3000",
        }
        with patch.dict(os.environ, env), patch(
            "local_api.accounts.requests.post", return_value=FakeGoogleResponse({"id_token": _id_token(claims)})
        ):
            start = self.client.get("/api/auth/google/start")
            state = start.headers["Location"].split("state=")[1].split("&")[0]
            callback = self.client.get(f"/api/auth/google/callback?code=abc&state={state}")
            self.assertEqual(callback.status_code, 302)
            me = self.client.get("/api/auth/me").get_json()
            self.assertEqual(me["user"]["name"], "José Conceição")

    def test_google_never_links_an_existing_email_account(self):
        self.register("ana@example.com")
        self.client.post("/api/auth/logout")  # clear register's session cookie
        claims = {
            "iss": "accounts.google.com",
            "aud": "client-id",
            "exp": int(time.time()) + 300,
            "sub": "google-sub-2",
            "email": "ana@example.com",
            "email_verified": True,
        }
        env = {"GOOGLE_CLIENT_ID": "client-id", "GOOGLE_CLIENT_SECRET": "secret"}
        with patch.dict(os.environ, env), patch(
            "local_api.accounts.requests.post", return_value=FakeGoogleResponse({"id_token": _id_token(claims)})
        ):
            start = self.client.get("/api/auth/google/start")
            state = start.headers["Location"].split("state=")[1].split("&")[0]
            callback = self.client.get(f"/api/auth/google/callback?code=abc&state={state}")
            self.assertEqual(callback.status_code, 302)
            self.assertIn("/conta?erro=google-conta-existente", callback.headers["Location"])
            # Creates no session
            self.assertIsNone(self.client.get("/api/auth/me").get_json()["user"])

            # Leaves google_sub null
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.email == "ana@example.com").one()
                self.assertIsNone(user.google_sub)
            finally:
                db.close()

    def test_google_refuses_email_verified_one(self):
        claims = {
            "iss": "accounts.google.com",
            "aud": "client-id",
            "exp": int(time.time()) + 300,
            "sub": "google-sub-int-verified",
            "email": "intverified@example.com",
            "email_verified": 1,
        }
        env = {"GOOGLE_CLIENT_ID": "client-id", "GOOGLE_CLIENT_SECRET": "secret"}
        with patch.dict(os.environ, env), patch(
            "local_api.accounts.requests.post", return_value=FakeGoogleResponse({"id_token": _id_token(claims)})
        ):
            start = self.client.get("/api/auth/google/start")
            state = start.headers["Location"].split("state=")[1].split("&")[0]
            callback = self.client.get(f"/api/auth/google/callback?code=abc&state={state}")
            self.assertIn("/conta?erro=google-token", callback.headers["Location"])
            self.assertIsNone(self.client.get("/api/auth/me").get_json()["user"])

    def test_google_refuses_another_audience(self):
        claims = {
            "iss": "accounts.google.com",
            "aud": "other-client",
            "exp": int(time.time()) + 300,
            "sub": "google-sub-3",
            "email": "gmail@example.com",
            "email_verified": True,
        }
        env = {"GOOGLE_CLIENT_ID": "client-id", "GOOGLE_CLIENT_SECRET": "secret"}
        with patch.dict(os.environ, env), patch(
            "local_api.accounts.requests.post", return_value=FakeGoogleResponse({"id_token": _id_token(claims)})
        ):
            start = self.client.get("/api/auth/google/start")
            state = start.headers["Location"].split("state=")[1].split("&")[0]
            callback = self.client.get(f"/api/auth/google/callback?code=abc&state={state}")
            self.assertIn("/conta?erro=google-token", callback.headers["Location"])
            self.assertIsNone(self.client.get("/api/auth/me").get_json()["user"])


class TestPasswordHashing(unittest.TestCase):
    def test_never_stores_the_password_and_accepts_it_back(self):
        stored = hash_password("segredo123")
        self.assertNotIn("segredo123", stored)
        self.assertTrue(stored.startswith("pbkdf2-sha256$"))
        self.assertTrue(verify_password("segredo123", stored))
        self.assertFalse(verify_password("outra-senha", stored))
        self.assertFalse(verify_password("segredo123", None))
        self.assertFalse(verify_password("segredo123", "lixo"))


if __name__ == "__main__":
    unittest.main()
