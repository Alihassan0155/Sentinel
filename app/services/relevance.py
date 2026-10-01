import re

from app.models import UserProfile


TERM_EQUIVALENTS = (
    {"ai", "ai ml", "artificial intelligence", "machine learning", "ml"},
)
SALARY_AMOUNT = re.compile(r"\$(?P<amount>\d+(?:,\d{3})*)(?P<suffix>\s*[kK])?")
SALARY_CONTEXT = re.compile(
    r"\b(salary|compensation|pay|wage|annual|per year|yearly)\b",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _matches_term(term: str, normalized_text: str) -> bool:
    normalized_term = _normalize(term)
    if not normalized_term:
        return False

    equivalent_terms = {normalized_term}
    for group in TERM_EQUIVALENTS:
        if normalized_term in group:
            equivalent_terms.update(group)

    padded_text = f" {normalized_text} "
    return any(
        f" {_normalize(candidate)} " in padded_text
        for candidate in equivalent_terms
    )


def _salary_amounts(text: str) -> list[int]:
    amounts = []

    for match in SALARY_AMOUNT.finditer(text):
        context_start = max(0, match.start() - 80)
        context_end = min(len(text), match.end() + 80)
        if not SALARY_CONTEXT.search(text[context_start:context_end]):
            continue

        amount = int(match.group("amount").replace(",", ""))
        if match.group("suffix"):
            amount *= 1000
        amounts.append(amount)

    return amounts


def assess_relevance(
    profile: UserProfile | None,
    *,
    category: str,
    summary: str,
    why_it_matters: str,
    entities: list[str],
    importance: str,
    change_type: str,
) -> dict:
    if profile is None:
        return {
            "relevance_score": 0,
            "reasons": ["No profile preferences configured."],
            "priority": "ignore",
        }

    content = " ".join([summary, why_it_matters, *entities])
    normalized_content = _normalize(content)
    normalized_category = _normalize(category)
    reasons = []
    score = 0

    preference_groups = (
        ("skill", profile.skills, 60, 60),
        ("role", profile.desired_roles, 45, 60),
        ("interest", profile.interests, 25, 50),
        ("location", profile.locations, 15, 25),
    )

    for label, preferences, points_per_match, group_limit in preference_groups:
        matches = [
            value
            for value in preferences
            if _matches_term(value, normalized_content)
        ]
        if matches:
            score += min(group_limit, points_per_match * len(matches))
            reasons.extend(f"Matches preferred {label}: {value}" for value in matches)

    if profile.degree and _matches_term(profile.degree, normalized_content):
        score += 10
        reasons.append(f"Matches preferred degree: {profile.degree}")

    if profile.salary_min is not None or profile.salary_max is not None:
        salary_match = any(
            (profile.salary_min is None or amount >= profile.salary_min)
            and (profile.salary_max is None or amount <= profile.salary_max)
            for amount in _salary_amounts(content)
        )
        if salary_match:
            score += 15
            reasons.append("Salary matches your preferred range.")

    category_matches = [
        value
        for value in profile.preferred_categories
        if _matches_term(value, normalized_category)
    ]
    if category_matches:
        reasons.extend(
            f"Matches preferred category: {value}"
            for value in category_matches
        )
        if score:
            score += 5

    if score and change_type in {"deadline", "eligibility", "requirement"}:
        score += 5
        reasons.append(f"Includes an actionable {change_type} update.")

    if not reasons:
        reasons.append("No profile preferences matched this change.")

    score = min(score, 100)
    if score >= 85 and importance == "critical":
        priority = "critical"
    elif score >= 60:
        priority = "high"
    elif score >= 30:
        priority = "medium"
    elif score >= 10:
        priority = "low"
    else:
        priority = "ignore"

    return {
        "relevance_score": score,
        "reasons": reasons,
        "priority": priority,
    }
