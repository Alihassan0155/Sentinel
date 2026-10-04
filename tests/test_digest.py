import unittest
from datetime import date

from app.services.digest import previous_week, render_digest


class DigestTests(unittest.TestCase):
    def test_previous_completed_week_starts_on_monday(self):
        self.assertEqual(previous_week(date(2026, 10, 2)), date(2026, 9, 21))
        self.assertEqual(previous_week(date(2026, 10, 5)), date(2026, 9, 28))

    def test_digest_includes_broader_intelligence(self):
        finding = {
            "summary": "New AI internship", "why_it_matters": "Matches Python skills",
            "recommendation": "recommended", "priority": "high",
            "relevance_score": 85, "suggested_action": "Prepare CV",
            "source_url": "https://example.com/jobs", "deadline": "October 15, 2026",
        }
        content = {
            "period_start": "2026-09-21", "period_end": "2026-09-27",
            "relevant_count": 1, "total_findings": 2,
            "top_opportunities": [finding],
            "upcoming_deadlines": [finding],
            "grouped_findings": {"high": {"jobs": [finding]}},
            "tracked_updates": [finding],
            "pending_actions": [{
                "title": "Prepare CV", "status": "pending",
                "deadline": "October 15, 2026", "source_url": "https://example.com/jobs",
            }],
            "deprioritized": [{**finding, "recommendation": "skip", "priority": "low"}],
            "trends": ["jobs: 1 relevant finding"],
        }
        subject, body = render_digest(content)
        self.assertIn("2026-09-21", subject)
        for expected in (
            "Most relevant opportunities", "Upcoming verified deadlines",
            "What changed: New AI internship", "Why it matters: Matches Python skills",
            "Recommendation: recommended", "Suggested action: Prepare CV",
            "Actions still pending", "Ignored or deprioritized", "Patterns this week",
        ):
            self.assertIn(expected, body)


if __name__ == "__main__":
    unittest.main()
