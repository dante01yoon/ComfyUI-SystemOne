import json
from dataclasses import dataclass, field

import pytest

from systemone.judgment import choose, score, yes_no

OPTIONS = "photo: a real photograph\nwatercolor"


@dataclass
class FakeBackend:
    answer: dict
    name: str = "fake"
    calls: list = field(default_factory=list)

    def ask(self, state, questions):
        self.calls.append((state, questions))
        return {qid: self.answer for qid in questions}


def choice_answer(confidence):
    return {"choice": "photo", "probabilities": {"photo": confidence, "watercolor": 1 - confidence}, "confidence": confidence}


@pytest.mark.parametrize(
    ("confidence", "min_confidence", "fallback", "choice", "confident"),
    [
        (0.9, 0.5, "safe", "photo", True),
        (0.5, 0.5, "safe", "photo", True),
        (0.4, 0.5, "safe", "safe", False),
        (0.4, 0.5, "", "photo", False),
    ],
)
def test_choice_fallback_applies_only_below_min_confidence(confidence, min_confidence, fallback, choice, confident):
    result = choose(FakeBackend(choice_answer(confidence)), "a cat", "Which style?", OPTIONS, min_confidence, fallback)
    assert (result.choice, result.confident) == (choice, confident)


def test_choice_sends_parsed_question_and_reports_it():
    backend = FakeBackend(choice_answer(0.8))
    result = choose(backend, '{"subject": "cat"}', "Which style?", OPTIONS, 0.0, "")
    state, questions = backend.calls[0]
    question = {"type": "choice", "instructions": "Which style?", "criteria": {"photo": "a real photograph", "watercolor": "watercolor"}}
    assert state == {"subject": "cat"}
    assert list(questions.values()) == [question]
    report = json.loads(result.report)
    assert (report["backend"], report["question"], report["answer"]["choice"]) == ("fake", question, "photo")
    assert result.preview.splitlines()[0] == "choice: photo"
    assert result.preview.index("photo ") < result.preview.index("watercolor ")


@pytest.mark.parametrize(("probability", "verdict"), [(0.49, False), (0.5, True), (0.51, True)])
def test_noul_verdict_at_threshold_boundary(probability, verdict):
    result = yes_no(FakeBackend({"noul": probability}), "s", "Is it night?", "", "", 0.5)
    assert (result.probability, result.verdict) == (probability, verdict)


@pytest.mark.parametrize(("value", "level"), [(-0.6, 0), (1.4, 1), (1.6, 2), (7.0, 2)])
def test_score_level_is_rounded_and_clamped(value, level):
    answer = {"score": value, "probabilities": {"0": 0.2, "1": 0.3, "2": 0.5}, "confidence": 0.5}
    result = score(FakeBackend(answer), "s", "How good?", "bad\nok\ngreat")
    assert (result.score, result.level) == (value, level)
    assert f"level: {level} " in result.preview
