# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Thesaurus parsing and full-text query expansion utilities."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable


Entry = dict[str, object]


def _strip_comment(line: str) -> str:
    """Remove unescaped Solr-style comments from one thesaurus line."""
    escaped = False
    for index, char in enumerate(line):
        if char == "\\" and not escaped:
            escaped = True
            continue
        if char == "#" and not escaped:
            return line[:index]
        escaped = False
    return line


def split_solr_values(value: str) -> list[str]:
    """Split comma-separated Solr synonym values while respecting backslash escapes."""
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ",":
            text = "".join(current).strip()
            if text:
                parts.append(text)
            current = []
        else:
            current.append(char)
    text = "".join(current).strip()
    if text:
        parts.append(text)
    return parts


def normalize_entries(entries: Iterable[Entry]) -> list[Entry]:
    """Normalize thesaurus entries into stable JSON-ready dictionaries."""
    normalized: list[Entry] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...], bool]] = set()
    for entry in entries:
        sources = _clean_terms(entry.get("source", []))
        targets = _clean_terms(entry.get("targets", []))
        bidirectional = bool(entry.get("bidirectional", False))
        if not sources or not targets:
            continue
        key = (tuple(sources), tuple(targets), bidirectional)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"source": sources, "targets": targets, "bidirectional": bidirectional})
    return normalized


def _clean_terms(terms: object) -> list[str]:
    """Lowercase and deduplicate thesaurus terms."""
    if isinstance(terms, str):
        raw_terms = [terms]
    elif isinstance(terms, Iterable):
        raw_terms = [str(term) for term in terms]
    else:
        raw_terms = []
    cleaned: list[str] = []
    for term in raw_terms:
        value = re.sub(r"\s+", " ", term.strip().lower())
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def parse_solr_synonyms(text: str) -> list[Entry]:
    """Parse Apache Solr synonym text into normalized JSON thesaurus entries.

    Supported forms are equivalent synonyms such as ``fast, quick, rapid`` and
    explicit mappings such as ``usa => united states, america``.
    """
    entries: list[Entry] = []
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        if "=>" in line:
            source, targets = line.split("=>", 1)
            entries.append({
                "source": split_solr_values(source),
                "targets": split_solr_values(targets),
                "bidirectional": False,
            })
        else:
            terms = split_solr_values(line)
            entries.append({"source": terms, "targets": terms, "bidirectional": True})
    return normalize_entries(entries)


def parse_thesaurus_json(payload: bytes | str) -> list[Entry]:
    """Parse a JSON thesaurus document into normalized entries."""
    data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    entries = data.get("entries", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("Thesaurus JSON must be a list or an object containing an entries list")
    return normalize_entries(entries)


def parse_thesaurus_payload(payload: bytes, source_format: str) -> list[Entry]:
    """Parse uploaded thesaurus bytes according to the declared source format."""
    if source_format == "json":
        return parse_thesaurus_json(payload)
    if source_format in {"solr", "solr_synonyms", "text"}:
        return parse_solr_synonyms(payload.decode("utf-8"))
    raise ValueError("source_format must be one of: solr_synonyms, solr, text, json")


def expand_query(query: str, entries: Iterable[Entry], max_terms: int = 24) -> tuple[str, list[str]]:
    """Expand a full-text query with matching thesaurus terms."""
    lowered_query = query.lower()
    additions: list[str] = []
    for entry in entries:
        sources = _clean_terms(entry.get("source", []))
        targets = _clean_terms(entry.get("targets", []))
        terms_to_match = sources + (targets if bool(entry.get("bidirectional", False)) else [])
        if not any(_term_in_query(term, lowered_query) for term in terms_to_match):
            continue
        candidate_terms = sources + targets
        for term in candidate_terms:
            if term not in lowered_query and term not in additions:
                additions.append(term)
                if len(additions) >= max_terms:
                    return _format_expanded_query(query, additions), additions
    return _format_expanded_query(query, additions), additions


def _term_in_query(term: str, lowered_query: str) -> bool:
    """Return whether a term or phrase appears in the query text."""
    if " " in term:
        return term in lowered_query
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered_query) is not None


def _format_expanded_query(query: str, additions: list[str]) -> str:
    """Build a PostgreSQL websearch_to_tsquery compatible OR expression."""
    if not additions:
        return query
    synonyms = " OR ".join(_quote_websearch(term) for term in additions)
    return f"{query} OR {synonyms}"


def _quote_websearch(term: str) -> str:
    """Quote phrases and special characters for websearch-style full-text syntax."""
    safe = term.replace('"', " ").strip()
    if re.search(r"\s|[-:()]", safe):
        return f'"{safe}"'
    return safe
