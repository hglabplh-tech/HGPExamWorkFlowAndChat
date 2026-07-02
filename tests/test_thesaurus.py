"""Thesaurus parsing and query-expansion tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import json

from backend.app.services.thesaurus import (
    expand_query,
    parse_solr_synonyms,
    parse_thesaurus_json,
    split_solr_values,
)


def test_solr_equivalent_synonyms_become_bidirectional_json_entries() -> None:
    """Solr equivalent lines can be stored as normalized JSON."""
    entries = parse_solr_synonyms("fast, quick, rapid\n# ignored\n")
    assert entries == [{
        "source": ["fast", "quick", "rapid"],
        "targets": ["fast", "quick", "rapid"],
        "bidirectional": True,
    }]


def test_solr_explicit_mapping_becomes_one_way_json_entry() -> None:
    """Solr mapping lines preserve their one-way expansion semantics."""
    entries = parse_solr_synonyms("usa => united states, america")
    assert entries == [{
        "source": ["usa"],
        "targets": ["united states", "america"],
        "bidirectional": False,
    }]


def test_solr_split_supports_escaped_commas() -> None:
    """Escaped commas remain part of the thesaurus term."""
    assert split_solr_values(r"m3\, apple silicon, arm64") == ["m3, apple silicon", "arm64"]


def test_json_thesaurus_import_is_normalized() -> None:
    """Uploaded JSON entries use the same normalized structure as text imports."""
    payload = json.dumps({"entries": [{"source": ["  CPU "], "targets": ["Processor"], "bidirectional": True}]})
    assert parse_thesaurus_json(payload) == [{
        "source": ["cpu"],
        "targets": ["processor"],
        "bidirectional": True,
    }]


def test_query_expansion_uses_matching_thesaurus_terms() -> None:
    """Full-text queries are expanded with matching synonyms before SQL ranking."""
    entries = parse_solr_synonyms("cpu, processor\nusa => united states, america")
    expanded, terms = expand_query("cpu architecture", entries)
    assert expanded == "cpu architecture OR processor"
    assert terms == ["processor"]


def test_query_expansion_quotes_phrases_for_postgres_websearch() -> None:
    """Phrase synonyms are quoted for PostgreSQL websearch_to_tsquery syntax."""
    entries = parse_solr_synonyms("usa => united states, america")
    expanded, terms = expand_query("history of usa", entries)
    assert expanded == 'history of usa OR "united states" OR america'
    assert terms == ["united states", "america"]
