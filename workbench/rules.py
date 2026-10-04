"""Numeric range checks done in code.

Small models are unreliable at questions like "is 4.8 above 5?", which is exactly what
applying an SOP limit needs. This module finds numeric rules in SOP text ("up to Rs 5 lakh",
"above 5 and up to 25", "must not exceed 10 percent") and works out, in Python, which ones a
given value satisfies. The result is given to the model as a fact.
"""
import re

_NUM = r"(\d+(?:\.\d+)?)"
_UNITS = {
    "lakh": r"lakhs?", "crore": r"crores?", "percent": r"(?:percent|%)", "mm/s": r"mm/s",
    "mm": r"mm(?!/)", "kg/cm2": r"kg/cm2", "bar": r"bar", "degrees": r"(?:degrees?|°\s?C)",
    "months": r"months?", "hours": r"hours?", "days": r"days?", "minutes": r"minutes?",
}
_VALUE = re.compile(_NUM + r"\s*(" + "|".join(_UNITS.values()) + r")", re.I)


def _unit_name(text):
    for name, pattern in _UNITS.items():
        if re.fullmatch(pattern, text.strip(), re.I):
            return name
    return None


def values_in(text):
    """{unit: [values]} for every number followed by a known unit."""
    found = {}
    for number, unit in _VALUE.findall(text):
        name = _unit_name(unit)
        if name:
            found.setdefault(name, [])
            if float(number) not in found[name]:
                found[name].append(float(number))
    return found


def _check(line, value, unit):
    """True / False if the line holds a rule in this unit, None if it does not."""
    q = r"(?:Rs\.?\s*)?" + _NUM + r"\s*" + _UNITS[unit]   # a quantity in this unit
    low = line.lower()
    patterns = [
        (r"(?:above|more than|greater than)\s+" + q + r"\s+(?:and|but)\s+(?:up to|not more than|less than or equal to)\s+" + q,
         lambda a, b: a < value <= b),
        (r"between\s+" + q + r"\s+and\s+" + q, lambda a, b: a <= value <= b),
        (r"(?:above|more than|greater than|exceeds|deeper than|over)\s+" + q, lambda a: value > a),
        (r"(?:less than|below|under)\s+" + q, lambda a: value < a),
        (r"(?:up to|not exceed|not more than|at most|maximum of)\s+" + q, lambda a: value <= a),
        (r"(?:at least|minimum of)\s+" + q, lambda a: value >= a),
        (q + r"\s+or more", lambda a: value >= a),
    ]
    for pattern, test in patterns:
        m = re.search(pattern, low, re.I)
        if m:
            return test(*[float(g) for g in m.groups()])
    return None


def range_notes(rule_text, values):
    """Text block listing which rule lines each value satisfies, or "" if none apply.

    `values` is {unit: [numbers]}. A unit with several different numbers is skipped:
    with more than one candidate the code cannot know which number a rule is about.
    """
    notes = []
    for unit, numbers in values.items():
        if len(numbers) != 1:
            continue
        value = numbers[0]
        results = []
        for line in rule_text.splitlines():
            line = line.strip()
            verdict = _check(line, value, unit) if line else None
            if verdict is not None:
                results.append(f'- "{line}" -> {"APPLIES" if verdict else "does not apply"}')
        if any("-> APPLIES" in r for r in results):
            shown = f"{value:g} {unit}"
            notes.append(f"Range check computed by the system for {shown}. It is exact: use its conclusion "
                         "in your own words, and do not copy this block or the word APPLIES into your reply.\n"
                         + "\n".join(results))
    return "\n\n".join(notes)
