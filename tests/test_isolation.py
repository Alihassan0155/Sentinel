"""Cross-account privacy regressions on PostgreSQL; all fixtures roll back."""
import os
import unittest
from datetime import date, datetime, timedelta
from secrets import token_urlsafe
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.auth import token_hash
from app.database import engine, get_db
from app.main import app
from app.models import (
    Account, ActionStep, AuthSession, CheckJob, Notification, Recommendation,
    UserProfile, WatchChange, WatchSnapshot, WatchSource, WeeklyDigest,
)
from app.services.digest import build_digest_content, dispatch_digest, generate_weekly_digest
from app.services.memory import recall, remember
from app.services.monitor import check_watch
from app.services.notification import dispatch_notification
from app.services.semantic import ChangeAnalysis


@unittest.skipUnless(os.getenv("SENTINEL_RUN_DB_TESTS") == "1", "requires local PostgreSQL")
class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        app.dependency_overrides[get_db] = lambda: self.db
        self.embedding = patch("app.services.memory._embedding", return_value=[1.0] + [0.0] * 767)
        self.embedding.start()
        self.accounts, self.clients = [], []
        self.headers = {"X-Sentinel-CSRF": "1", "Origin": "http://localhost:3000"}
        for name in ["Alice", "Bob"]:
            account = Account(email=f"{name.lower()}-{uuid4()}@example.com", name=name, password_hash="unused")
            self.db.add(account)
            self.db.flush()
            token = token_urlsafe(32)
            self.db.add(AuthSession(token_hash=token_hash(token), account_id=account.id,
                                    expires_at=datetime.now() + timedelta(days=1)))
            client = TestClient(app)
            client.cookies.set("sentinel_session", token)
            self.accounts.append(account)
            self.clients.append(client)
        self.watches, self.changes, self.actions, self.alerts, self.jobs = [], [], [], [], []
        shared_url = f"https://example.com/{uuid4()}"
        for account in [*self.accounts, None]:
            name = account.name if account else "Legacy"
            watch = WatchSource(account_id=account.id if account else None, name=name,
                                url=shared_url, category="jobs", active=False, check_interval_minutes=30)
            self.db.add(watch)
            self.db.flush()
            snapshot = WatchSnapshot(watch_source_id=watch.id, content_hash="old", content_text="old")
            self.db.add(snapshot)
            self.db.flush()
            change = WatchChange(watch_source_id=watch.id, snapshot_id=snapshot.id, importance="high",
                                 change_type="content", summary=f"{name} private finding", why_it_matters="Opportunity",
                                 should_notify=True, entities=[], detected_at=datetime(2026, 10, 1))
            self.db.add(change)
            self.db.flush()
            action = ActionStep(watch_change_id=change.id, position=1, title=f"{name} private action", status="pending")
            alert = Notification(watch_change_id=change.id, watch_source_id=watch.id, status="pending",
                                 subject=f"{name} private alert", body="Private details", urgent=True)
            job = CheckJob(watch_source_id=watch.id, mode="normal", status="pending")
            self.db.add_all([action, alert, job, Recommendation(watch_change_id=change.id,
                recommendation="recommended", priority="high", reasons=["Match"], relevance_score=85)])
            if account:
                self.db.add(UserProfile(account_id=account.id, skills=[name], interests=[name]))
                remember(self.db, account_id=account.id, kind="preference", source_key="profile", content=f"{name} private memory")
            self.db.flush()
            self.watches.append(watch); self.changes.append(change); self.actions.append(action)
            self.alerts.append(alert); self.jobs.append(job)
        self.db.commit()

    def tearDown(self):
        for client in self.clients:
            client.close()
        app.dependency_overrides.clear()
        self.embedding.stop()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def test_lists_and_profile_are_private(self):
        for i, client in enumerate(self.clients):
            self.assertEqual([row["id"] for row in client.get("/watches").json()], [self.watches[i].id])
            changes = client.get("/changes").json()
            self.assertEqual([row["id"] for row in changes], [self.changes[i].id])
            self.assertEqual([row["id"] for row in changes[0]["actions"]], [self.actions[i].id])
            self.assertEqual([row["id"] for row in client.get("/notifications").json()["notifications"]], [self.alerts[i].id])
            self.assertEqual(client.get("/profile").json()["skills"], [self.accounts[i].name])
            memories = client.get("/memory").json()
            self.assertEqual([row["content"] for row in memories], [f"{self.accounts[i].name} private memory"])
            results = client.get("/memory/search", params={"q": "private memory"}).json()
            self.assertEqual([row["content"] for row in results], [f"{self.accounts[i].name} private memory"])

    def test_guessed_ids_cannot_read_or_mutate_other_or_legacy_data(self):
        client = self.clients[0]
        for i in [1, 2]:
            attempts = [
                ("POST", f"/watches/{self.watches[i].id}/check", {}),
                ("POST", f"/watches/{self.watches[i].id}/test-change", {}),
                ("PATCH", f"/watches/{self.watches[i].id}", {"active": True}),
                ("GET", f"/watches/check-jobs/{self.jobs[i].id}", None),
                ("GET", f"/actions/changes/{self.changes[i].id}", None),
                ("POST", f"/actions/changes/{self.changes[i].id}", {}),
                ("PATCH", f"/actions/{self.actions[i].id}", {"status": "completed"}),
                ("POST", f"/memory/changes/{self.changes[i].id}/feedback", {"decision": "saved"}),
                ("POST", "/memory", {"kind": "decision", "content": "Private reference", "change_id": self.changes[i].id}),
            ]
            for method, path, body in attempts:
                with self.subTest(path=path):
                    response = client.request(method, path, json=body, headers=self.headers)
                    self.assertEqual(response.status_code, 404, response.text)
            self.db.refresh(self.actions[i]); self.db.refresh(self.watches[i])
            self.assertEqual(self.actions[i].status, "pending")
            self.assertFalse(self.watches[i].active)
        response = client.patch(f"/actions/{self.actions[0].id}", json={"status": "completed"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_same_url_and_memory_keys_are_independent(self):
        url = f"https://example.com/new-{uuid4()}"
        for i, client in enumerate(self.clients):
            response = client.post("/watches", headers=self.headers, json={"name": "Own source", "url": url,
                "category": "jobs", "account_id": self.accounts[1 - i].id})
            self.assertEqual(response.status_code, 200, response.text)
            created = self.db.get(WatchSource, response.json()["id"])
            self.assertEqual(created.account_id, self.accounts[i].id)
            duplicate = client.post("/watches", headers=self.headers, json={"name": "Duplicate", "url": url, "category": "jobs"})
            self.assertEqual(duplicate.status_code, 409)
        result = self.clients[0].put("/profile", headers=self.headers, json={"skills": ["Python"]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.clients[1].get("/profile").json()["skills"], ["Bob"])
        # Removing Alice's profile memory cannot remove Bob's same-key memory.
        self.assertEqual(self.clients[0].put("/profile", headers=self.headers, json={}).status_code, 200)
        self.assertEqual(self.clients[0].get("/memory").json(), [])
        self.assertEqual(self.clients[1].get("/memory").json()[0]["content"], "Bob private memory")

    def test_new_profile_row_is_allocated_for_its_account(self):
        profile = self.db.query(UserProfile).filter(UserProfile.account_id == self.accounts[0].id).one()
        self.db.delete(profile)
        self.db.commit()
        self.assertEqual(self.clients[0].get("/profile").json()["skills"], [])
        response = self.clients[0].put("/profile", headers=self.headers, json={"skills": ["New account skill"]})
        self.assertEqual(response.status_code, 200, response.text)
        created = self.db.get(UserProfile, response.json()["id"])
        self.assertEqual(created.account_id, self.accounts[0].id)
        self.assertEqual(self.clients[1].get("/profile").json()["skills"], ["Bob"])

    def test_weekly_digests_and_pending_actions_are_private(self):
        digests = []
        for i, account in enumerate(self.accounts):
            content = build_digest_content(self.db, date(2026, 9, 28), account_id=account.id, today=date(2026, 10, 5))
            self.assertEqual(content["total_findings"], 1)
            self.assertEqual([row["step_id"] for row in content["pending_actions"]], [self.actions[i].id])
            digest = generate_weekly_digest(self.db, date(2026, 9, 28), account_id=account.id, today=date(2026, 10, 5))
            digests.append(digest)
            self.assertNotIn(self.accounts[1 - i].name, digest.body)
            self.assertNotIn("Legacy", digest.body)
            self.assertEqual([row["id"] for row in self.clients[i].get("/digests/weekly").json()], [digest.id])
        self.assertNotEqual(digests[0].id, digests[1].id)
        self.assertEqual(self.clients[0].get(f"/digests/weekly/{digests[1].id}").status_code, 404)
        self.assertEqual(self.clients[0].post(f"/digests/weekly/{digests[1].id}/send", headers=self.headers).status_code, 404)

    def test_delivery_only_targets_resource_owner(self):
        with patch("app.services.notification.email_configured", return_value=True), patch("app.api.notifications.email_configured", return_value=True), patch("app.services.notification.send_email") as send:
            response = self.clients[0].post("/notifications/dispatch", headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["processed"], 1)
            send.assert_called_once_with(self.alerts[0].subject, self.alerts[0].body, recipient=self.accounts[0].email)
            dispatch_notification(self.db, self.alerts[2])
            self.assertEqual(send.call_count, 1)
            self.assertEqual(self.alerts[1].status, "pending")
        digest = generate_weekly_digest(self.db, date(2026, 9, 28), account_id=self.accounts[1].id, today=date(2026, 10, 5))
        with patch("app.services.digest.email_configured", return_value=True), patch("app.services.digest.send_email") as send:
            dispatch_digest(self.db, digest)
            send.assert_called_once_with(digest.subject, digest.body, recipient=self.accounts[1].email)
            legacy = WeeklyDigest(account_id=None, period_start=date(2025, 1, 6), period_end=date(2025, 1, 12),
                                  status="pending", subject="Legacy", body="Shared data", content={})
            self.db.add(legacy); self.db.commit()
            dispatch_digest(self.db, legacy)
            self.assertEqual(send.call_count, 1)

    def test_worker_uses_watch_owner_profile_and_memories(self):
        analysis = ChangeAnalysis(importance="high", change_type="content", summary="New Python job",
                                 why_it_matters="New role", should_notify=False, entities=[])
        for i, account in enumerate(self.accounts):
            seen = []
            def assess(profile, **kwargs):
                seen.append(profile.account_id)
                return {"relevance_score": 80, "reasons": ["Match"], "priority": "high"}
            with patch("app.services.orchestration.analyze_change", return_value=analysis), patch("app.services.orchestration.assess_relevance", side_effect=assess):
                check_watch(self.watches[i], self.db, content_override=f"new {i}", allow_notification=False, allow_investigation=False)
            self.assertTrue(seen)
            self.assertEqual(set(seen), {account.id})
            memories = recall(self.db, "private", account_id=account.id)
            self.assertFalse(any(self.accounts[1 - i].name in row["content"] for row in memories))
            self.assertTrue(any(row["kind"] == "finding" for row in memories))
        with self.assertRaises(ValueError):
            check_watch(self.watches[2], self.db, content_override="unassigned", allow_notification=False)
