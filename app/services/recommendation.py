"""Deterministic attention decisions using existing relevance and verified facts."""

import re

from app.models import UserProfile


def _fact_value(result: dict, key: str) -> str | None:
    fact = result.get(key)
    return fact.get("value", "") if isinstance(fact, dict) else None


def _amounts(value: str) -> list[int]:
    amounts = []
    for number, suffix in re.findall(r"\$\s*(\d[\d,]*)(\s*[kK])?", value):
        amount = int(number.replace(",", ""))
        amounts.append(amount * 1000 if suffix else amount)
    return amounts


def recommend(
    *,
    profile: UserProfile | None,
    relevance: dict,
    memories: list[dict] | None = None,
    investigation: dict | None = None,
    investigation_status: str | None = None,
) -> dict:
    score = relevance["relevance_score"]
    reasons = list(relevance["reasons"])
    result = investigation or {}
    blockers = []

    if profile is not None:
        location = _fact_value(result, "location")
        if location and profile.locations:
            if any(value.casefold() in location.casefold() for value in profile.locations):
                reasons.append(f"Verified location matches your preference: {location}.")
            else:
                blockers.append("Verified location differs from your preferred locations.")

        salary = _fact_value(result, "salary")
        if salary and profile.salary_min is not None:
            amounts = _amounts(salary)
            if amounts and max(amounts) < profile.salary_min:
                blockers.append("Verified salary is below your minimum.")
            elif amounts:
                reasons.append("Verified salary meets your minimum.")

    if _fact_value(result, "deadline"):
        reasons.append("Investigation verified an application deadline.")
    if result.get("application_steps"):
        reasons.append("Investigation found supported application steps.")

    decision_memories = [
        memory for memory in (memories or [])
        if memory.get("kind") == "decision" and memory.get("similarity", 0) >= 0.78
    ]
    if decision_memories:
        decision = decision_memories[0].get("metadata", {}).get("decision")
        if decision in {"saved", "interested", "applied"}:
            reasons.append("You previously valued a similar opportunity.")
        elif decision in {"dismissed", "irrelevant"}:
            reasons.append("You previously dismissed a similar opportunity.")

    if score < 30:
        recommendation = "skip"
        priority = "ignore"
    elif blockers:
        recommendation = "skip"
        priority = "low"
        reasons.extend(blockers)
    elif score >= 60:
        recommendation = "recommended"
        priority = relevance["priority"]
    else:
        recommendation = "review"
        priority = "medium" if score >= 40 else "low"

    if investigation_status == "failed" and recommendation == "recommended":
        recommendation = "review"
        priority = "medium"
        reasons.append("Investigation could not verify the details yet.")

    return {
        "recommendation": recommendation,
        "reasons": list(dict.fromkeys(reasons)),
        "priority": priority,
        "relevance_score": score,
    }
