"""Graph routing against PostgreSQL; opt in with SENTINEL_RUN_DB_TESTS=1."""

import hashlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.database import engine
from app.models import Account, WatchSnapshot, WatchSource
from app.schemas.investigation import InvestigationResult
from app.services.monitor import check_watch
from app.services.semantic import ChangeAnalysis


@unittest.skipUnless(os.getenv("SENTINEL_RUN_DB_TESTS") == "1", "requires local PostgreSQL")
class OrchestrationTests(unittest.TestCase):
    def test_conditional_routes(self):
        with engine.connect() as connection:
            outer = connection.begin()
            db = Session(bind=connection, join_transaction_mode="create_savepoint")
            try:
                account = Account(email=f"graph-{uuid4()}@example.com", name="Graph test", password_hash="unused")
                db.add(account)
                db.flush()
                watch = WatchSource(
                    account_id=account.id,
                    name="graph-test", url=f"https://example.invalid/{uuid4()}",
                    category="jobs", check_interval_minutes=30, active=False,
                )
                db.add(watch)
                db.flush()
                db.add(WatchSnapshot(
                    watch_source_id=watch.id,
                    content_hash=hashlib.sha256(b"same").hexdigest(),
                    content_text="same",
                ))
                db.commit()

                result = check_watch(watch, db, content_override="same", allow_notification=False)
                self.assertEqual(result["workflow_steps"], ["monitor"])

                analysis = ChangeAnalysis(
                    importance="high", change_type="content",
                    summary="Python internship", why_it_matters="New role",
                    should_notify=False, entities=[],
                )
                with (
                    patch("app.services.orchestration.analyze_change", return_value=analysis),
                    patch("app.services.orchestration.assess_relevance", return_value={
                        "relevance_score": 0, "reasons": ["No match"], "priority": "ignore",
                    }),
                    patch("app.services.orchestration.relevant_context", return_value=[]),
                ):
                    result = check_watch(
                        watch, db, content_override="different", allow_notification=False,
                    )
                self.assertEqual(result["workflow_steps"],
                                 ["monitor", "analyze", "relevance"])

                low = {"relevance_score": 15, "reasons": ["Weak match"],
                       "priority": "low"}
                with (
                    patch("app.services.orchestration.analyze_change", return_value=analysis),
                    patch("app.services.orchestration.assess_relevance", return_value=low),
                    patch("app.services.orchestration.relevant_context", return_value=[]),
                    patch("app.services.orchestration.remember", return_value=1),
                    patch("app.services.orchestration.investigate_change") as investigate,
                ):
                    result = check_watch(
                        watch, db, content_override="low priority", allow_notification=False,
                    )
                self.assertEqual(result["workflow_steps"], [
                    "monitor", "analyze", "relevance", "recommendation", "memory",
                ])
                investigate.assert_not_called()

                high = {"relevance_score": 80, "reasons": ["Matches Python"],
                        "priority": "high"}
                with (
                    patch("app.services.orchestration.analyze_change", return_value=analysis),
                    patch("app.services.orchestration.assess_relevance", return_value=high),
                    patch("app.services.orchestration.relevant_context", return_value=[]),
                    patch("app.services.orchestration.investigate_change",
                          return_value=InvestigationResult()),
                    patch("app.services.orchestration.remember", return_value=1),
                ):
                    result = check_watch(
                        watch, db, content_override="high priority",
                        allow_notification=False,
                    )
                self.assertEqual(result["workflow_steps"], [
                    "monitor", "analyze", "relevance", "recommendation",
                    "investigation", "recommendation", "action", "memory",
                ])
                self.assertEqual(result["recommendation"]["recommendation"], "recommended")
                self.assertTrue(result["actions"])

                alert_analysis = analysis.model_copy(update={"should_notify": True})
                outbox = SimpleNamespace(id=999, status="pending", reason=None)
                with (
                    patch("app.services.orchestration.analyze_change", return_value=alert_analysis),
                    patch("app.services.orchestration.assess_relevance", return_value=high),
                    patch("app.services.orchestration.relevant_context", return_value=[]),
                    patch("app.services.orchestration.investigate_change",
                          return_value=InvestigationResult()),
                    patch("app.services.orchestration.remember", return_value=1),
                    patch("app.services.orchestration.queue_notification", return_value=outbox),
                    patch("app.services.orchestration.dispatch_notification", return_value=outbox),
                ):
                    result = check_watch(
                        watch, db, content_override="important alert",
                    )
                self.assertEqual(result["workflow_steps"][-3:],
                                 ["action", "notify", "memory"])
                self.assertEqual(result["notification"]["status"], "pending")
            finally:
                db.close()
                outer.rollback()


if __name__ == "__main__":
    unittest.main()
