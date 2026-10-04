import unittest
from datetime import date
from types import SimpleNamespace

from app.services.notification import alert_decision, compose_email


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.change = SimpleNamespace(
            should_notify=True,
            summary="New AI internship",
            why_it_matters="Matches your Python skills",
        )

    def test_high_priority_recommendation_alerts(self):
        decision = {"recommendation": "recommended", "priority": "high"}
        self.assertEqual(
            alert_decision(self.change, decision, None, today=date(2026, 10, 2)),
            (True, False),
        )

    def test_urgent_verified_deadline_promotes_medium_priority(self):
        decision = {"recommendation": "recommended", "priority": "medium"}
        investigation = {"deadline": {
            "value": "October 3, 2026",
            "source_urls": ["https://example.com"],
        }}
        self.assertEqual(
            alert_decision(self.change, decision, investigation, today=date(2026, 10, 2)),
            (True, True),
        )
        investigation["deadline"]["value"] = "3 October 2026"
        self.assertEqual(
            alert_decision(self.change, decision, investigation, today=date(2026, 10, 2)),
            (True, True),
        )

    def test_unverified_deadline_and_skipped_finding_do_not_alert(self):
        decision = {"recommendation": "recommended", "priority": "medium"}
        investigation = {"deadline": {"value": "October 3, 2026", "source_urls": []}}
        self.assertEqual(
            alert_decision(self.change, decision, investigation, today=date(2026, 10, 2)),
            (False, False),
        )
        self.assertEqual(
            alert_decision(self.change, {"recommendation": "skip", "priority": "high"},
                           None, today=date(2026, 10, 2)),
            (False, False),
        )

    def test_email_contains_action_deadline_and_source(self):
        decision = {"recommendation": "recommended", "priority": "high"}
        investigation = {"deadline": {
            "value": "2026-10-03", "source_urls": ["https://example.com"],
        }}
        subject, body = compose_email(
            self.change, decision, [SimpleNamespace(title="Prepare CV")],
            "https://example.com", investigation,
        )
        self.assertIn("New AI internship", subject)
        for expected in ("Matches your Python skills", "Prepare CV", "2026-10-03",
                         "https://example.com"):
            self.assertIn(expected, body)


if __name__ == "__main__":
    unittest.main()
