"""Turn verified investigation facts into small, traceable action steps."""

import re

from app.models import UserProfile


RESOURCE_ALIASES = {
    "CV": ("cv", "curriculum vitae", "resume", "résumé"),
    "transcript": ("transcript", "academic record"),
    "cover letter": ("cover letter", "motivation letter", "statement of motivation"),
    "portfolio": ("portfolio",),
    "recommendation letter": ("recommendation letter", "reference letter"),
}


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def _resources_in(value: str) -> list[str]:
    normalized = f" {_normalize(value)} "
    return [
        name for name, aliases in RESOURCE_ALIASES.items()
        if any(f" {_normalize(alias)} " in normalized for alias in aliases)
    ]


def _available(resource: str, available_resources: list[str]) -> bool:
    target = _resources_in(resource)
    if target:
        return any(
            any(name in _resources_in(candidate) for name in target)
            for candidate in available_resources
        )
    return any(
        _normalize(resource) == _normalize(candidate)
        for candidate in available_resources
    )


def build_action_plan(
    investigation: dict | None,
    profile: UserProfile | None,
    source_url: str,
) -> list[dict]:
    result = investigation or {}
    available_resources = (profile.available_resources or []) if profile else []
    deadline_fact = result.get("deadline") or {}
    deadline = deadline_fact.get("value") if isinstance(deadline_fact, dict) else None
    steps = []
    seen_resources = set()

    for fact in result.get("eligibility", []):
        value = fact.get("value", "").strip()
        if value:
            steps.append({
                "title": f"Confirm eligibility: {value}",
                "resource": None,
                "resource_status": None,
                "source_urls": fact.get("source_urls", []),
                "supporting_quote": fact.get("supporting_quote"),
                "deadline": deadline,
            })

    for fact in result.get("required_skills", []):
        value = fact.get("value", "").strip()
        if value:
            declared = bool(profile and any(
                _normalize(value) == _normalize(skill)
                for skill in (profile.skills or [])
            ))
            steps.append({
                "title": f"Confirm required skill: {value}",
                "resource": value,
                "resource_status": "available" if declared else "unconfirmed",
                "source_urls": fact.get("source_urls", []),
                "supporting_quote": fact.get("supporting_quote"),
                "deadline": deadline,
            })

    for fact in result.get("required_documents", []):
        value = fact.get("value", "").strip()
        if not value:
            continue
        resources = _resources_in(value) or [value]
        for resource in resources:
            if resource in seen_resources:
                continue
            seen_resources.add(resource)
            available = _available(resource, available_resources)
            steps.append({
                "title": f"Check and prepare {resource}" if available else f"Prepare {resource}",
                "resource": resource,
                "resource_status": "available" if available else "missing",
                "source_urls": fact.get("source_urls", []),
                "supporting_quote": fact.get("supporting_quote"),
                "deadline": deadline,
            })

    for fact in result.get("application_steps", []):
        value = fact.get("value", "").strip()
        if value:
            steps.append({
                "title": value,
                "resource": None,
                "resource_status": None,
                "source_urls": fact.get("source_urls", []),
                "supporting_quote": fact.get("supporting_quote"),
                "deadline": deadline,
            })

    if not steps:
        steps.append({
            "title": "Review the source and confirm the next application step",
            "resource": None,
            "resource_status": None,
            "source_urls": [source_url],
            "supporting_quote": None,
            "deadline": deadline,
        })

    return [{"position": index, **step} for index, step in enumerate(steps, 1)]
