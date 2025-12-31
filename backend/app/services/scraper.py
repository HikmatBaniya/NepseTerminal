from __future__ import annotations

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


def _can_fetch(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    parser = RobotFileParser()
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(robots_url, headers={"User-Agent": settings.scrape_user_agent})
            if resp.status_code >= 400:
                return True
            parser.parse(resp.text.splitlines())
            return parser.can_fetch(settings.scrape_user_agent, url)
    except Exception:
        return True


def fetch_page(url: str, respect_robots: bool = True) -> dict[str, str]:
    if respect_robots and not _can_fetch(url):
        return {"error": "Blocked by robots.txt"}

    headers = {"User-Agent": settings.scrape_user_agent}
    with httpx.Client(timeout=20) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    text = " ".join(chunk.strip() for chunk in soup.get_text(" ").split())

    return {
        "title": title,
        "text": text,
        "html": resp.text,
    }