"""Website fetch helper and LangGraph watch-check entry point."""

import re

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import WatchSource
from app.services.browser import needs_browser, render_page
from app.services.network import get_page, website_client

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)


def fetch_page(url: str) -> str:
    with website_client() as client:
        response = get_page(client, url)

    content = _extract_text(response.text)
    if needs_browser(response.text, content):
        _, rendered_html = render_page(str(response.url), USER_AGENT)
        content = _extract_text(rendered_html)
    return content


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # Preserve block boundaries so diffing is meaningful.
    raw_text = soup.get_text(separator="\n")

    lines = []

    for line in raw_text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)

def check_watch(
    watch: WatchSource,
    db: Session,
    *,
    content_override: str | None = None,
    allow_investigation: bool = True,
    allow_notification: bool = True,
) -> dict:
    from app.services.orchestration import run_watch_graph

    return run_watch_graph(
        watch, db, fetch_page, content_override=content_override,
        allow_investigation=allow_investigation,
        allow_notification=allow_notification,
    )
