from dataclasses import dataclass
from typing import Literal

from .backends import MAX_IMAGES_PER_CALL, Backend, ImageSource
from .judgment import ask_one, bar, probability_lines, to_report
from .questions import choice_question, noul_question

NEUTRAL_STATE = "An image is attached."
COUNT_WORDS = {2: "Two", 3: "Three", 4: "Four"}

RejectWhen = Literal["yes", "no"]


@dataclass(frozen=True)
class ImageCheckResult:
    passed_indices: tuple[int, ...]
    probabilities: tuple[float, ...]
    report: str
    preview: str


@dataclass(frozen=True)
class Heat:
    name: str
    probabilities: dict[int, float]


@dataclass(frozen=True)
class PickResult:
    index: int
    confidence: float
    heats: tuple[Heat, ...]
    report: str
    preview: str


def _state(context: str) -> dict | str:
    context = context.strip()
    return {"prompt": context} if context else NEUTRAL_STATE


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def image_options(count: int) -> dict[str, str]:
    return {f"image_{n}": f"the {ordinal(n)} attached image" for n in range(1, count + 1)}


def check_images(
    backend: Backend,
    images: list[ImageSource],
    context: str,
    instructions: str,
    true_criteria: str,
    false_criteria: str,
    reject_when: RejectWhen,
    threshold: float,
) -> ImageCheckResult:
    question = noul_question(instructions, true_criteria, false_criteria)
    state = _state(context)
    probabilities, records = [], []
    for image in images:
        answer, record = ask_one(backend, state, question, [image])
        probabilities.append(float(answer["noul"]))
        records.append(record)
    passed = tuple(i for i, p in enumerate(probabilities) if (p >= threshold) != (reject_when == "yes"))
    lines = [f"passed {len(passed)}/{len(images)} (reject when {reject_when} at threshold {threshold:.2f})", ""]
    lines += [
        f"image {i + 1}  {bar(p)} {p:.2f}  {'PASS' if i in passed else 'REJECT'}" for i, p in enumerate(probabilities)
    ]
    return ImageCheckResult(passed, tuple(probabilities), to_report(records), "\n".join(lines))


def _run_heat(backend: Backend, images: list[ImageSource], indices: list[int], state, instructions: str):
    if len(indices) == 1:
        return indices[0], 1.0, {indices[0]: 1.0}, None
    options = image_options(len(indices))
    order_note = f"{COUNT_WORDS[len(indices)]} images are attached in order: image_1 is the 1st attached image, and so on."
    question = choice_question(f"{order_note} {instructions.strip()}", options)
    answer, record = ask_one(backend, state, question, [images[i] for i in indices])
    original = dict(zip(options, indices))
    probabilities = {original[label]: float(p) for label, p in answer["probabilities"].items()}
    return original[answer["choice"]], float(answer["confidence"]), probabilities, record


def pick_best(backend: Backend, images: list[ImageSource], context: str, instructions: str) -> PickResult:
    if not images:
        raise ValueError("Pick Best Image needs at least one image.")
    state = _state(context)
    candidates, confidence = list(range(len(images))), 1.0
    heats, records = [], []
    round_number = 0
    while len(candidates) > 1:
        round_number += 1
        groups = [candidates[i : i + MAX_IMAGES_PER_CALL] for i in range(0, len(candidates), MAX_IMAGES_PER_CALL)]
        winners = []
        for number, group in enumerate(groups, start=1):
            winner, confidence, probabilities, record = _run_heat(backend, images, group, state, instructions)
            name = "final" if len(groups) == 1 else f"round {round_number} heat {number}"
            heats.append(Heat(name, probabilities))
            records += [record] if record else []
            winners.append(winner)
        candidates = winners
    index = candidates[0]

    lines = [f"best: image {index + 1}", f"confidence: {confidence:.2f}"]
    for heat in heats:
        ranked = {f"image {i + 1}": p for i, p in heat.probabilities.items()}
        lines += ["", f"{heat.name}:", *probability_lines(ranked)]
    return PickResult(index, confidence, tuple(heats), to_report(records), "\n".join(lines))
