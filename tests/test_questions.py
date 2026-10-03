import pytest

from systemone.questions import lookup, noul_question, parse_levels, parse_mapping, parse_options, parse_state


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('  {"mood": "calm"} ', {"mood": "calm"}),
        ("[1, 2]", [1, 2]),
        ("a cat by the window", "a cat by the window"),
        ('"quoted"', '"quoted"'),
        ("42", "42"),
    ],
)
def test_parse_state(text, expected):
    assert parse_state(text) == expected


def test_parse_options_accepts_described_and_bare_labels():
    assert parse_options(" photo : a real photograph\n\nanime\n") == {"photo": "a real photograph", "anime": "anime"}


@pytest.mark.parametrize(
    ("parse", "text", "message"),
    [
        (parse_options, "photo\nphoto: again", "Duplicate"),
        (parse_options, "only\n\n", "at least 2"),
        (parse_levels, "low", "at least 2"),
        (parse_mapping, "photo -> 30", "key => value"),
        (parse_mapping, "a => 1\na => 2", "Duplicate"),
    ],
)
def test_parsers_reject_bad_text(parse, text, message):
    with pytest.raises(ValueError, match=message):
        parse(text)


def test_parse_levels_keeps_order():
    assert parse_levels("bad\n\n ok \ngreat") == ["bad", "ok", "great"]


@pytest.mark.parametrize(
    ("mapping", "key", "expected"),
    [
        ("photo => 30\n* => 20", " photo ", "30"),
        ("photo => 30\n* => 20", "anime", "20"),
        ("2 => , masterpiece", "2", ", masterpiece"),
    ],
)
def test_lookup(mapping, key, expected):
    assert lookup(parse_mapping(mapping), key) == expected


def test_lookup_without_match_or_default_names_known_keys():
    with pytest.raises(ValueError, match="'photo'"):
        lookup(parse_mapping("photo => 30"), "anime")


@pytest.mark.parametrize(
    ("true_criteria", "false_criteria", "expected"),
    [
        ("", " ", {"type": "noul", "instructions": "q"}),
        ("yes", "no", {"type": "noul", "instructions": "q", "criteria": {"true": "yes", "false": "no"}}),
    ],
)
def test_noul_question_criteria_optional(true_criteria, false_criteria, expected):
    assert noul_question("q", true_criteria, false_criteria) == expected


def test_noul_question_rejects_one_sided_criteria():
    with pytest.raises(ValueError, match="both"):
        noul_question("q", "yes", "")
