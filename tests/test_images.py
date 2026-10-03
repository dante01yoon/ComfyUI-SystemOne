import json
from dataclasses import dataclass, field

import pytest

from systemone.images import check_images, image_options, pick_best

@dataclass(frozen=True)
class FakeImage:
    id: int

    def __call__(self, long_side):
        return f"jpeg-{self.id}@{long_side}".encode()


IMAGES = [FakeImage(i) for i in range(8)]


@dataclass
class Call:
    state: object
    question: dict
    images: list


@dataclass
class FakeImageBackend:
    noul_by_image: dict = field(default_factory=dict)
    score_by_image: dict = field(default_factory=dict)
    name: str = "fake-clef"
    supports_images: bool = True
    calls: list = field(default_factory=list)

    def ask(self, state, questions, images=None):
        (qid, question), = questions.items()
        self.calls.append(Call(state, question, list(images or [])))
        if question["type"] == "noul":
            return {qid: {"noul": self.noul_by_image[images[0]]}}
        scores = [self.score_by_image[image] for image in images]
        total = sum(scores)
        probabilities = {label: s / total for label, s in zip(question["criteria"], scores)}
        choice = max(probabilities, key=probabilities.get)
        return {qid: {"choice": choice, "probabilities": probabilities, "confidence": probabilities[choice]}}


def check(probabilities, reject_when, threshold=0.5, context="a cat"):
    backend = FakeImageBackend(noul_by_image=dict(zip(IMAGES, probabilities)))
    images = IMAGES[: len(probabilities)]
    return backend, check_images(backend, images, context, "Malformed hands?", "", "", reject_when, threshold)


@pytest.mark.parametrize(
    ("reject_when", "passed"),
    [
        ("yes", (0,)),
        ("no", (1, 2)),
    ],
)
def test_check_rejects_by_answer_at_threshold_boundary(reject_when, passed):
    _, result = check([0.49, 0.5, 0.51], reject_when)
    assert result.passed_indices == passed
    assert result.probabilities == (0.49, 0.5, 0.51)


def test_check_sends_one_image_per_call_with_prompt_state():
    backend, result = check([0.1, 0.9], "yes")
    assert [len(call.images) for call in backend.calls] == [1, 1]
    assert [call.images[0] for call in backend.calls] == IMAGES[:2]
    assert {json.dumps(call.state) for call in backend.calls} == {json.dumps({"prompt": "a cat"})}
    assert backend.calls[0].question == {"type": "noul", "instructions": "Malformed hands?"}
    assert [entry["image_count"] for entry in json.loads(result.report)] == [1, 1]


def test_check_without_context_sends_neutral_text_state():
    backend, _ = check([0.1], "yes", context="  ")
    assert isinstance(backend.calls[0].state, str) and backend.calls[0].state.strip()


def test_check_zero_pass_lists_every_image_as_rejected():
    _, result = check([0.8, 0.9], "yes")
    assert result.passed_indices == ()
    assert result.preview.splitlines()[0].startswith("passed 0/2")
    assert [line.split()[-1] for line in result.preview.splitlines()[2:]] == ["REJECT", "REJECT"]
    assert [line.split()[:2] for line in result.preview.splitlines()[2:]] == [["image", "1"], ["image", "2"]]


def pick(scores):
    backend = FakeImageBackend(score_by_image=dict(zip(IMAGES, scores)))
    return backend, pick_best(backend, IMAGES[: len(scores)], "a cat", "Which image best matches the prompt?")


@pytest.mark.parametrize(
    ("scores", "index", "call_sizes"),
    [
        ([5], 0, []),
        ([1, 7, 2], 1, [3]),
        ([1, 2, 3, 4, 1, 9], 5, [4, 2, 2]),
        ([1, 9, 3, 4, 1, 2], 1, [4, 2, 2]),
        ([1, 2, 3, 4, 9], 4, [4, 2]),
    ],
)
def test_pick_best_runs_heats_and_maps_back_to_original_index(scores, index, call_sizes):
    backend, result = pick(scores)
    assert result.index == index
    assert [len(call.images) for call in backend.calls] == call_sizes


def test_pick_best_final_receives_heat_winners_in_order():
    backend, result = pick([1, 2, 3, 4, 1, 9])
    final = backend.calls[-1]
    assert final.images == [IMAGES[3], IMAGES[5]]
    assert result.heats[-1].name == "final"
    assert result.heats[-1].probabilities == {3: 4 / 13, 5: 9 / 13}
    assert result.confidence == 9 / 13
    assert result.preview.splitlines()[0] == "best: image 6"


def test_pick_best_single_image_makes_no_call():
    backend, result = pick([5])
    assert (backend.calls, result.index, result.confidence) == ([], 0, 1.0)


def test_pick_best_question_uses_ordinal_options_and_says_images_are_in_order():
    backend, _ = pick([1, 2, 3])
    question = backend.calls[0].question
    assert question["type"] == "choice"
    assert question["criteria"] == {
        "image_1": "the 1st attached image",
        "image_2": "the 2nd attached image",
        "image_3": "the 3rd attached image",
    }
    assert question["instructions"].startswith("Three images are attached in order")
    assert question["instructions"].endswith("Which image best matches the prompt?")
    assert backend.calls[0].state == {"prompt": "a cat"}


@pytest.mark.parametrize(("n", "description"), [(4, "the 4th attached image"), (11, "the 11th attached image"), (21, "the 21st attached image")])
def test_image_options_ordinals(n, description):
    assert image_options(n)[f"image_{n}"] == description
