import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models import UserProfile, WatchChange
from app.schemas.investigation import (
    EvidenceFact,
    InvestigationDraft,
    InvestigationResult,
    InvestigationSource,
)
from app.services.semantic import MODEL, client


logger = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)
MAX_RELATED_LINKS = 3
MAX_PAGE_CHARS = 12000
MAX_EVIDENCE_CHARS = 36000
LINK_HINTS = {
    "apply",
    "application",
    "career",
    "deadline",
    "detail",
    "eligibility",
    "employment",
    "fellowship",
    "how to apply",
    "internship",
    "job",
    "position",
    "requirement",
    "scholarship",
    "vacancy",
}
STOP_WORDS = {
    "about", "exact", "find", "information", "need", "process", "provide",
    "what", "which", "with", "your",
}


@dataclass(frozen=True)
class EvidencePage:
    url: str
    title: str
    source_type: str
    retrieved_at: datetime
    content: str


def plan_questions(category: str, change_type: str, summary: str) -> list[str]:
    subject = f"{category} {summary}".lower()

    if any(word in subject for word in ("scholarship", "grant", "fellowship", "funding")):
        questions = [
            "What are the eligibility criteria, including age and degree restrictions?",
            "What is the award amount or funding coverage?",
            "What is the exact application deadline?",
            "Which documents are required?",
            "What are the application steps and official application URL?",
        ]
    elif any(word in subject for word in ("job", "career", "employment", "vacancy", "internship", "engineer", "position")):
        questions = [
            "What are the required skills and qualifications?",
            "What degree and experience are required?",
            "What is the exact application deadline?",
            "What salary or compensation is offered?",
            "What is the work location and work arrangement?",
            "What are the application steps and official application URL?",
            "Which documents must applicants submit?",
        ]
    else:
        questions = [
            "What are the eligibility or participation requirements?",
            "What is the exact deadline or effective date?",
            "What costs, benefits, or amounts are stated?",
            "What steps or documents are required to act on this update?",
            "Where is the official detail or application page?",
        ]

    if change_type == "deadline":
        questions.insert(0, "What is the exact deadline, including timezone if stated?")
    elif change_type in {"eligibility", "requirement"}:
        questions.insert(0, "What exact eligibility criteria or requirements changed?")

    return list(dict.fromkeys(questions))


def _clean_page(response: httpx.Response, source_type: str) -> EvidencePage:
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in soup.get_text(separator="\n").splitlines()
    ]
    content = "\n".join(line for line in lines if line)

    return EvidencePage(
        url=str(response.url),
        title=title,
        source_type=source_type,
        retrieved_at=datetime.now(timezone.utc),
        content=content[:MAX_PAGE_CHARS],
    )


def _needs_browser(html: str, page: EvidencePage) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    has_app_root = soup.find(id=re.compile(r"^(root|app)$", re.IGNORECASE))
    return len(page.content) < 1000 and bool(soup.find_all("script")) and (
        len(soup.find_all("script")) >= 2 or has_app_root is not None
    )


def _render_page(url: str) -> tuple[str, str]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            try:
                page.wait_for_load_state("networkidle", timeout=4000)
            except PlaywrightTimeoutError:
                pass
            return page.url, page.content()
        finally:
            browser.close()


def _fetch_evidence_page(
    http: httpx.Client,
    url: str,
    source_type: str,
) -> tuple[str, EvidencePage]:
    response = http.get(url)
    response.raise_for_status()
    html = response.text
    page = _clean_page(response, source_type)

    if _needs_browser(html, page):
        logger.info("Using Playwright for JavaScript-rendered page %s", url)
        rendered_url, html = _render_page(url)
        rendered_response = httpx.Response(
            200,
            request=httpx.Request("GET", rendered_url),
            text=html,
        )
        page = _clean_page(rendered_response, source_type)

    return html, page


def _related_links(
    html: str,
    base_url: str,
    questions: list[str],
) -> list[tuple[str, str, bool]]:
    base = urlparse(base_url)
    soup = BeautifulSoup(html, "html.parser")
    question_terms = {
        term
        for term in re.findall(r"[a-z]{4,}", " ".join(questions).lower())
        if term not in STOP_WORDS
    }
    ranked: list[tuple[int, str, str, bool]] = []
    seen = {base_url}

    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"].strip())
        parsed = urlparse(href)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or href in seen
        ):
            continue
        seen.add(href)

        label = anchor.get_text(" ", strip=True)
        searchable = f"{label} {parsed.path}".lower()
        hint_score = sum(3 for hint in LINK_HINTS if hint in searchable)
        question_score = sum(1 for term in question_terms if term in searchable)
        score = hint_score + question_score
        if score:
            same_host = parsed.netloc.lower() == base.netloc.lower()
            ranked.append((score, href, label, same_host))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        (href, label, same_host)
        for _, href, label, same_host in ranked[:MAX_RELATED_LINKS]
    ]


def collect_evidence(
    original_url: str,
    questions: list[str],
) -> list[EvidencePage]:
    pages = []
    with httpx.Client(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as http:
        original_html, original_page = _fetch_evidence_page(
            http,
            original_url,
            "original",
        )
        related_links = _related_links(
            original_html,
            original_page.url,
            questions,
        )
        linked_resources = "\n".join(
            f"{label or 'Relevant link'}: {href}"
            for href, label, _ in related_links
        )
        if linked_resources:
            original_page = EvidencePage(
                url=original_page.url,
                title=original_page.title,
                source_type=original_page.source_type,
                retrieved_at=original_page.retrieved_at,
                content=(
                    f"{original_page.content}\n\n"
                    f"Relevant linked URLs:\n{linked_resources}"
                )[:MAX_PAGE_CHARS],
            )
        pages.append(original_page)

        for href, label, same_host in related_links:
            if not same_host:
                continue
            source_type = (
                "application"
                if any(word in f"{label} {href}".lower() for word in ("apply", "application"))
                else "details"
            )
            try:
                response = http.get(href)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    continue
                if _needs_browser(response.text, _clean_page(response, source_type)):
                    logger.info(
                        "Using Playwright for JavaScript-rendered page %s",
                        href,
                    )
                    rendered_url, rendered_html = _render_page(href)
                    response = httpx.Response(
                        200,
                        request=httpx.Request("GET", rendered_url),
                        text=rendered_html,
                    )
                pages.append(_clean_page(response, source_type))
            except httpx.HTTPError:
                logger.warning("Could not fetch investigation link %s", href, exc_info=True)

    return pages


def _normalize_quote(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def _verify_fact(
    fact: EvidenceFact,
    pages_by_url: dict[str, EvidencePage],
) -> EvidenceFact | None:
    quote = _normalize_quote(fact.supporting_quote)
    if not fact.value.strip() or len(quote) < 8:
        return None
    value_numbers = re.findall(r"\d+", fact.value)
    quote_numbers = re.findall(r"\d+", fact.supporting_quote)
    if any(number not in quote_numbers for number in value_numbers):
        return None

    supported_urls = [
        url
        for url in fact.source_urls
        if url in pages_by_url
        and quote in _normalize_quote(pages_by_url[url].content)
    ]
    if not supported_urls:
        return None

    return EvidenceFact(
        value=fact.value.strip(),
        source_urls=list(dict.fromkeys(supported_urls)),
        supporting_quote=fact.supporting_quote.strip(),
    )


def _verify_result(
    draft: InvestigationDraft,
    pages: list[EvidencePage],
) -> InvestigationResult:
    pages_by_url = {page.url: page for page in pages}
    missing = list(draft.missing_information)
    values = draft.model_dump()
    missing_labels = {
        "title": "title",
        "deadline": "deadline",
        "eligibility": "eligibility requirements",
        "required_skills": "required skills",
        "salary": "salary",
        "location": "location",
        "application_steps": "application steps",
        "required_documents": "required documents",
    }

    for field, label in missing_labels.items():
        value = values[field]
        if isinstance(value, list):
            verified = [
                fact
                for item in value
                if (fact := _verify_fact(EvidenceFact.model_validate(item), pages_by_url))
            ]
            values[field] = [fact.model_dump() for fact in verified]
            if len(verified) < len(value):
                missing.append(label)
        elif value is not None:
            verified_fact = _verify_fact(
                EvidenceFact.model_validate(value),
                pages_by_url,
            )
            values[field] = verified_fact.model_dump() if verified_fact else None
            if verified_fact is None:
                missing.append(label)

    values["missing_information"] = list(dict.fromkeys(missing))
    values["sources"] = [
        InvestigationSource(
            url=page.url,
            title=page.title,
            source_type=page.source_type,
            retrieved_at=page.retrieved_at,
        ).model_dump(mode="json")
        for page in pages
    ]
    return InvestigationResult.model_validate(values)


def investigate_change(
    change: WatchChange,
    original_url: str,
    category: str,
    profile: UserProfile | None,
    memories: list[dict] | None = None,
) -> InvestigationResult:
    questions = plan_questions(category, change.change_type, change.summary)
    pages = collect_evidence(original_url, questions)
    remaining_chars = MAX_EVIDENCE_CHARS
    evidence = []
    prompt_pages = []
    for page in pages:
        content = page.content[:remaining_chars]
        remaining_chars -= len(content)
        prompt_pages.append(page)
        evidence.append(
            f"URL: {page.url}\n"
            f"Title: {page.title}\n"
            f"Source type: {page.source_type}\n"
            f"Content:\n{content}"
        )
        if remaining_chars <= 0:
            break

    profile_data = None
    if profile is not None:
        profile_data = {
            "skills": profile.skills,
            "degree": profile.degree,
            "interests": profile.interests,
            "desired_roles": profile.desired_roles,
            "locations": profile.locations,
            "preferred_categories": profile.preferred_categories,
            "salary_min": profile.salary_min,
            "salary_max": profile.salary_max,
        }

    prompt = f"""
You are Sentinel's evidence-grounded investigation agent. Investigate only to answer the questions below.

Original change:
Title/source: {change.summary}
Category: {category}
Change type: {change.change_type}
Why it matters: {change.why_it_matters}
Detected entities: {change.entities}

Relevant user profile:
{profile_data}

Relevant prior memories (personal context only; never use as source evidence):
{[memory['content'][:500] for memory in (memories or [])[:5]]}

Investigation questions:
{questions}

Evidence pages:
{chr(10).join(evidence)}

Rules:
- Use only facts explicitly supported by the evidence pages.
- For each fact, return source_urls using the exact URL shown above and a supporting_quote copied verbatim from that page.
- If a fact is absent or uncertain, return null for scalar fields or an empty list for list fields, and identify it in missing_information.
- Never infer a deadline, salary, eligibility rule, location, or application requirement.
- Keep values concise. Do not return facts without a supporting quote and source URL.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": InvestigationDraft,
        },
    )
    if response.parsed is None:
        raise RuntimeError("Gemini returned no structured investigation result.")

    return _verify_result(response.parsed, prompt_pages)
