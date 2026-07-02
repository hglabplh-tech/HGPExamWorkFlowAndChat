"""Transparent percentage conversions for configurable grading frameworks.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""


EUROPEAN_ECTS_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "IS", "LI", "NO", "CH",
}


def _band(percent: float, bands: list[tuple[float, str]]) -> str:
    """Return the first descending threshold label containing the percentage."""
    return next(label for minimum, label in bands if percent >= minimum)


def convert_grades(score: float, maximum: float) -> dict[str, object]:
    """Convert a raw score without claiming institutional equivalence."""
    percent = max(0.0, min(100.0, 100 * score / maximum if maximum else 0.0))
    ects = _band(percent, [(90, "A"), (80, "B"), (70, "C"), (60, "D"), (50, "E"), (0, "F")])
    german = _band(percent, [(95, "1.0"), (90, "1.3"), (85, "1.7"), (80, "2.0"), (75, "2.3"), (70, "2.7"), (65, "3.0"), (60, "3.3"), (55, "3.7"), (50, "4.0"), (0, "5.0")])
    british = _band(percent, [(70, "First-class / Distinction"), (60, "Upper second / Merit"), (50, "Lower second / Pass"), (40, "Third-class / Pass"), (0, "Fail")])
    us_letter = _band(percent, [(93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"), (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"), (63, "D"), (60, "D-"), (0, "F")])
    gpa = _band(percent, [(93, "4.0"), (90, "3.7"), (87, "3.3"), (83, "3.0"), (80, "2.7"), (77, "2.3"), (73, "2.0"), (70, "1.7"), (67, "1.3"), (63, "1.0"), (60, "0.7"), (0, "0.0")])
    return {
        "percentage": round(percent, 2),
        "ects": ects,
        "germany": german,
        "united_kingdom": british,
        "united_states": {"letter": us_letter, "gpa_4": gpa},
        "european_country_ects": {country: ects for country in sorted(EUROPEAN_ECTS_COUNTRIES)},
        "disclaimer": "Indicative conversion only; the institution's published scale and ECTS distribution table prevail.",
    }
