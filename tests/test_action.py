import unittest

from app.models import UserProfile
from app.services.action import build_action_plan


class ActionPlanTests(unittest.TestCase):
    def test_resources_and_evidence_are_preserved(self):
        profile = UserProfile(skills=["Python"], available_resources=["My CV", "transcript"])
        investigation = {
            "deadline": {"value": "October 15", "source_urls": ["https://example.com"]},
            "required_documents": [{
                "value": "CV, transcript, and cover letter",
                "source_urls": ["https://example.com/apply"],
                "supporting_quote": "Submit a CV, transcript, and cover letter",
            }],
            "application_steps": [{
                "value": "Submit the application form",
                "source_urls": ["https://example.com/apply"],
                "supporting_quote": "Submit the application form",
            }],
        }
        plan = build_action_plan(investigation, profile, "https://example.com")
        self.assertEqual([step["resource_status"] for step in plan[:3]],
                         ["available", "available", "missing"])
        self.assertEqual(plan[2]["deadline"], "October 15")
        self.assertEqual(plan[2]["source_urls"], ["https://example.com/apply"])
        self.assertEqual(plan[-1]["title"], "Submit the application form")

    def test_unknown_skills_are_checks(self):
        profile = UserProfile(skills=[], available_resources=[])
        plan = build_action_plan({"required_skills": [{
            "value": "Python", "source_urls": ["https://example.com"],
            "supporting_quote": "Python required",
        }]}, profile, "https://example.com")
        self.assertEqual(plan[0]["resource_status"], "unconfirmed")

    def test_missing_investigation_produces_source_review(self):
        plan = build_action_plan(None, None, "https://example.com")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["source_urls"], ["https://example.com"])


if __name__ == "__main__":
    unittest.main()
