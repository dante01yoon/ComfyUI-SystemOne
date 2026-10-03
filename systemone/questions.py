import json

DEFAULT_KEY = "*"


def parse_state(text: str) -> str | dict | list:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    return parsed if isinstance(parsed, (dict, list)) else text


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_options(text: str) -> dict[str, str]:
    options: dict[str, str] = {}
    for line in _lines(text):
        label, _, description = (part.strip() for part in line.partition(":"))
        if not label:
            raise ValueError(f"Option line has no label: {line!r}")
        if label in options:
            raise ValueError(f"Duplicate option label: {label!r}")
        options[label] = description or label
    if len(options) < 2:
        raise ValueError("Choice needs at least 2 options, one per line ('label: description').")
    return options


def parse_levels(text: str) -> list[str]:
    levels = _lines(text)
    if len(levels) < 2:
        raise ValueError("Score needs at least 2 levels, one per line from lowest to highest.")
    return levels


def parse_mapping(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in _lines(text):
        key, arrow, value = line.partition("=>")
        key = key.strip()
        if not arrow or not key:
            raise ValueError(f"Mapping line must look like 'key => value': {line!r}")
        if key in mapping:
            raise ValueError(f"Duplicate mapping key: {key!r}")
        mapping[key] = value.strip()
    return mapping


def lookup(mapping: dict[str, str], key: str) -> str:
    key = key.strip()
    if key in mapping:
        return mapping[key]
    if DEFAULT_KEY in mapping:
        return mapping[DEFAULT_KEY]
    known = ", ".join(repr(k) for k in mapping) or "none"
    raise ValueError(f"No mapping for key {key!r} and no '* => default' line. Known keys: {known}.")


def choice_question(instructions: str, options: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": options}


def noul_question(instructions: str, true_criteria: str, false_criteria: str) -> dict:
    question = {"type": "noul", "instructions": instructions}
    true_criteria, false_criteria = true_criteria.strip(), false_criteria.strip()
    if bool(true_criteria) != bool(false_criteria):
        raise ValueError("Give both true_criteria and false_criteria, or neither.")
    if true_criteria:
        question["criteria"] = {"true": true_criteria, "false": false_criteria}
    return question


def score_question(instructions: str, levels: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": levels}
