"""Fetch and normalize article / README text for scoring."""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "AI-News-Agent/1.0 (content reader)"
_SKIP_SUFFIXES = (".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".webp")


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _github_raw_readme_urls(page_url: str) -> list[str]:
    match = re.search(r"github\.com/([^/]+)/([^/#?]+)", page_url)
    if not match:
        return []
    owner, repo = match.group(1), match.group(2)
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md",
        f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README",
        f"https://api.github.com/repos/{owner}/{repo}/readme",
    ]


async def fetch_page_text(
    client: httpx.AsyncClient,
    url: str,
    max_chars: int = 12000,
) -> str:
    if not url or not url.startswith("http"):
        return ""
    if url.lower().endswith(_SKIP_SUFFIXES):
        return ""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html, text/plain, text/markdown"}
    try:
        if "github.com" in url:
            for candidate in _github_raw_readme_urls(url):
                resp = await client.get(candidate, headers={**headers, "Accept": "text/plain"})
                if resp.status_code == 200 and resp.text.strip():
                    text = resp.text
                    if candidate.endswith("/readme"):
                        text = html_to_text(text) if "<" in text[:200] else text
                    return text[:max_chars]
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "pdf" in ctype or "image" in ctype:
            return ""
        body = resp.text
        if "html" in ctype or body.lstrip().startswith("<"):
            return html_to_text(body)[:max_chars]
        return body[:max_chars]
    except Exception as exc:
        logger.debug("Fetch page failed [%s]: %s", url, exc)
        return ""
