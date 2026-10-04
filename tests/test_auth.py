import unittest
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.auth import current_account, password_hash, router, verify_password
from app.database import get_db
from app.models.auth import Account, AuthAttempt, AuthSession


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        for model in [Account, AuthSession, AuthAttempt]:
            model.__table__.create(self.engine)
        app = FastAPI()
        app.include_router(router)
        @app.get("/private")
        def private(account=Depends(current_account)):
            return {"id": account.id}
        @app.post("/private")
        def mutate(account=Depends(current_account)):
            return {"id": account.id}
        def db():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_db] = db
        self.client = TestClient(app)
        self.headers = {"X-Sentinel-CSRF": "1", "Origin": "http://localhost:3000"}
        self.credentials = {"email": "test@example.com", "password": "strong-password-123"}

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def signup(self):
        return self.client.post("/auth/signup", json={**self.credentials, "name": "Test"}, headers=self.headers)

    def test_signup_logout_login_revokes_session(self):
        self.assertEqual(self.client.get("/private").status_code, 401)
        response = self.signup()
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.text)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        token = self.client.cookies.get("sentinel_session")
        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/private").status_code, 403)
        self.assertEqual(self.client.post("/private", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post("/auth/logout", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/private").status_code, 401)
        self.client.cookies.set("sentinel_session", token)
        self.assertEqual(self.client.get("/private").status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/auth/login", json=self.credentials, headers=self.headers).status_code, 200)

    def test_validation_duplicate_and_wrong_password(self):
        self.assertEqual(self.signup().status_code, 201)
        self.assertEqual(self.signup().status_code, 409)
        response = self.client.post("/auth/login", json={**self.credentials, "password": "wrong-password"}, headers=self.headers)
        self.assertEqual(response.status_code, 401)
        response = self.client.post("/auth/signup", json={**self.credentials, "name": " ", "password": "short"}, headers=self.headers)
        self.assertEqual(response.status_code, 422)
        with Session(self.engine) as db:
            account = db.query(Account).one()
            self.assertNotEqual(account.password_hash, self.credentials["password"])
            self.assertTrue(verify_password(self.credentials["password"], account.password_hash))

    def test_expiry_csrf_and_throttle(self):
        self.assertEqual(self.signup().status_code, 201)
        with Session(self.engine) as db:
            db.query(AuthSession).one().expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        headers = {**self.headers, "Origin": "https://evil.example"}
        self.assertEqual(self.client.post("/auth/login", json=self.credentials, headers=headers).status_code, 403)
        with Session(self.engine) as db:
            db.query(AuthAttempt).one().count = 30
            db.commit()
        self.assertEqual(self.client.post("/auth/login", json=self.credentials, headers=self.headers).status_code, 429)

    def test_hashes_are_salted(self):
        a, b = password_hash("same-password"), password_hash("same-password")
        self.assertNotEqual(a, b)
        self.assertFalse(verify_password("different-password", a))


if __name__ == "__main__":
    unittest.main()
