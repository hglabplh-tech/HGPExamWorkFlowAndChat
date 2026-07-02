"""Evidence-oriented Internet similarity, grammar, APA, and fact review.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import re
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from .asag import jaccard


def candidate_passages(text: str, limit: int = 5) -> list[str]:
    """Select substantial passages suitable for similarity queries."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.split()) >= 8]
    return sorted(sentences, key=len, reverse=True)[:limit]


def check_apa_citations(text: str) -> dict:
    """Check basic APA author-year citations and reference-list presence."""
    parenthetical = re.findall(r"\([A-ZÄÖÜ][\w'-]+(?:\s+et al\.)?,\s*\d{4}[a-z]?\)", text)
    narrative = re.findall(r"[A-ZÄÖÜ][\w'-]+\s+\(\d{4}[a-z]?\)", text)
    has_references = bool(re.search(r"(?im)^\s*(references|literaturverzeichnis|quellen)\s*$", text))
    return {
        "citation_count": len(parenthetical) + len(narrative),
        "has_reference_section": has_references,
        "warnings": ([] if parenthetical or narrative else ["No recognizable APA author-year citation found"])
        + ([] if has_references else ["No reference section heading found"]),
    }


async def grammar_review(text: str) -> dict:
    """Call a configured LanguageTool-compatible service without sending data by default."""
    settings = get_settings()
    if not settings.grammar_service_url:
        return {"status": "not_configured", "issues": []}
    async with httpx.AsyncClient(timeout=settings.internet_search_timeout_seconds) as client:
        response = await client.post(settings.grammar_service_url, data={"text": text, "language": "auto"})
        response.raise_for_status()
    matches = response.json().get("matches", [])
    return {"status": "completed", "issue_count": len(matches), "issues": matches[:100]}


async def internet_similarity(text: str, maximum_queries: int = 5) -> dict:
    """Query an administrator-configured search API and retain explainable matches."""
    settings = get_settings()
    if not settings.internet_search_endpoint:
        return {"status": "not_configured", "matches": [], "message": "Configure INTERNET_SEARCH_ENDPOINT and its API key"}
    headers = {"Authorization": f"Bearer {settings.internet_search_api_key.get_secret_value()}"}
    matches = []
    async with httpx.AsyncClient(timeout=settings.internet_search_timeout_seconds, follow_redirects=False) as client:
        for passage in candidate_passages(text, maximum_queries):
            response = await client.get(settings.internet_search_endpoint, params={"q": f'"{passage[:240]}"', "count": 5}, headers=headers)
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or payload.get("webPages", {}).get("value", [])
            for result in results[:5]:
                url = result.get("url") or result.get("link")
                excerpt = result.get("snippet") or result.get("description") or ""
                if not url or urlparse(url).scheme not in {"http", "https"}:
                    continue
                matches.append({"url": url, "title": result.get("title") or result.get("name") or "", "query_passage": passage, "excerpt": excerpt, "lexical_similarity": round(jaccard(passage, excerpt), 4)})
    matches.sort(key=lambda item: item["lexical_similarity"], reverse=True)
    return {"status": "completed", "matches": matches[:25], "maximum_similarity": max((item["lexical_similarity"] for item in matches), default=0.0)}


async def fact_check_knowledge_text(text: str, *, rubric: str = "general", topic: str | None = None, maximum_queries: int = 5) -> dict:
    """Check imported knowledge against administrator-approved trusted search sources."""
    settings = get_settings()
    trusted_domains = [domain.strip().casefold() for domain in settings.trusted_fact_source_domains.split(",") if domain.strip()]
    if not settings.internet_search_endpoint:
        return {
            "status": "not_configured",
            "rubric": rubric,
            "topic": topic,
            "trusted_domains": trusted_domains,
            "decision": "manual_review_required",
            "message": "Configure INTERNET_SEARCH_ENDPOINT before automated trusted-source fact checking.",
        }
    headers = {"Authorization": f"Bearer {settings.internet_search_api_key.get_secret_value()}"}
    checks = []
    async with httpx.AsyncClient(timeout=settings.internet_search_timeout_seconds, follow_redirects=False) as client:
        for passage in candidate_passages(text, maximum_queries):
            query = f'{topic or rubric} "{passage[:220]}"'
            response = await client.get(settings.internet_search_endpoint, params={"q": query, "count": 5}, headers=headers)
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or payload.get("webPages", {}).get("value", [])
            trusted = []
            for result in results[:5]:
                url = result.get("url") or result.get("link")
                if not url:
                    continue
                host = urlparse(url).hostname or ""
                if not any(host == domain or host.endswith(f".{domain}") for domain in trusted_domains):
                    continue
                excerpt = result.get("snippet") or result.get("description") or ""
                trusted.append({
                    "url": url,
                    "title": result.get("title") or result.get("name") or "",
                    "excerpt": excerpt,
                    "support_similarity": round(jaccard(passage, excerpt), 4),
                })
            checks.append({"claim": passage, "trusted_matches": trusted, "supported": any(item["support_similarity"] >= 0.05 for item in trusted)})
    unsupported = [item for item in checks if not item["supported"]]
    return {
        "status": "completed",
        "rubric": rubric,
        "topic": topic,
        "trusted_domains": trusted_domains,
        "checks": checks,
        "decision": "accepted" if not unsupported else "manual_review_required",
        "unsupported_count": len(unsupported),
    }


async def review_exam_text(text: str, *, maximum_queries: int = 5, search_internet: bool = True, check_grammar: bool = True, check_apa: bool = True) -> dict:
    """Build review evidence while reserving misconduct decisions for instructors."""
    similarity = await internet_similarity(text, maximum_queries) if search_internet else {"status": "disabled", "matches": []}
    grammar = await grammar_review(text) if check_grammar else {"status": "disabled", "issues": []}
    apa = check_apa_citations(text) if check_apa else {"status": "disabled"}
    return {"internet_similarity": similarity, "grammar": grammar, "apa": apa, "decision": "instructor_review_required", "notice": "Similarity is evidence, not an automatic plagiarism finding."}
