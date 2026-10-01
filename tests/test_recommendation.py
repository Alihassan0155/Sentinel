import unittest

from app.models import UserProfile
from app.services.recommendation import recommend


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.profile = UserProfile(
            skills=["Python"], interests=[], desired_roles=[],
            locations=["Remote"], preferred_categories=[], salary_min=80000,
        )
        self.relevance = {
            "relevance_score": 75,
            "reasons": ["Matches preferred skill: Python"],
            "priority": "high",
        }

    def test_verified_salary_constraint_blocks_recommendation(self):
        result = recommend(
            profile=self.profile,
            relevance=self.relevance,
            investigation={"salary": {"value": "$60k"}},
        )
        self.assertEqual(result["recommendation"], "skip")
        self.assertIn("Verified salary is below your minimum.", result["reasons"])

    def test_failed_investigation_requires_review(self):
        result = recommend(
            profile=self.profile, relevance=self.relevance,
            investigation_status="failed",
        )
        self.assertEqual(result["recommendation"], "review")

    def test_supported_details_and_feedback_are_explained(self):
        result = recommend(
            profile=self.profile, relevance=self.relevance,
            investigation={
                "location": {"value": "Remote"},
                "application_steps": [{"value": "Apply online"}],
            },
            memories=[{
                "kind": "decision", "similarity": 0.91,
                "metadata": {"decision": "saved"},
            }],
        )
        self.assertEqual(result["recommendation"], "recommended")
        self.assertTrue(any("previously valued" in reason for reason in result["reasons"]))
        self.assertTrue(any("Verified location" in reason for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
