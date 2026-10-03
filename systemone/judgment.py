import json
import time
from dataclasses import dataclass
from typing import Any

from .backends import Backend, ImageSource
from .questions import (
    choice_question,
    noul_question,
    parse_levels,
    parse_options,
    parse_state,
    score_question,
)

QUESTION_ID = "q"
BAR_WIDTH = 20


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    confidence: float
    confident: bool
    report: str
    preview: str


@dataclass(frozen=True)
class NoulResult:
    probability: float
    verdict: bool
    report: str
    preview: str


@dataclass(frozen=True)
class ScoreResult:
    score: float
    level: int
    confidence: float
    report: str
    preview: str


def ask_one(backend: Backend, state: Any, question: dict, images: list[ImageSource] | None = None) -> tuple[dict, dict]:
    started = time.perf_counter()
    answers = backend.ask(state, {QUESTION_ID: question}, images)
    latency_ms = round((time.perf_counter() - started) * 1000)
    if QUESTION_ID not in answers:
        raise RuntimeError(f"{backend.name} returned no answer for the question.")
    answer = answers[QUESTION_ID]
    record = {"backend": backend.name, "question": question, "answer": answer, "latency_ms": latency_ms}
    if images:
        record["image_count"] = len(images)
    return answer, record


def to_report(record: Any) -> str:
    # Laya answers can hold numpy scalars; float() makes them JSON-safe.
    return json.dumps(record, default=float)


def _ask(backend: Backend, state_text: str, question: dict) -> tuple[dict, str]:
    answer, record = ask_one(backend, parse_state(state_text), question)
    return answer, to_report(record)


def bar(probability: float) -> str:
    filled = round(probability * BAR_WIDTH)
    return "#" * filled + "." * (BAR_WIDTH - filled)


def probability_lines(probabilities: dict[str, Any], labels: dict[str, str] | None = None) -> list[str]:
    ranked = sorted(((label, float(p)) for label, p in probabilities.items()), key=lambda item: item[1], reverse=True)
    width = max(len((labels or {}).get(label, label)) for label, _ in ranked)
    return [f"{(labels or {}).get(label, label):<{width}}  {bar(p)} {p:.2f}" for label, p in ranked]


def choose(
    backend: Backend, state: str, instructions: str, options_text: str, min_confidence: float, fallback: str
) -> ChoiceResult:
    answer, report = _ask(backend, state, choice_question(instructions, parse_options(options_text)))
    confidence = float(answer["confidence"])
    confident = confidence >= min_confidence
    choice = answer["choice"] if confident or not fallback else fallback
    header = f"choice: {choice}" + ("" if choice == answer["choice"] else f" (fallback; model said {answer['choice']})")
    preview = "\n".join([header, f"confidence: {confidence:.2f}", "", *probability_lines(answer["probabilities"])])
    return ChoiceResult(choice, confidence, confident, report, preview)


def yes_no(
    backend: Backend, state: str, instructions: str, true_criteria: str, false_criteria: str, threshold: float
) -> NoulResult:
    answer, report = _ask(backend, state, noul_question(instructions, true_criteria, false_criteria))
    probability = float(answer["noul"])
    verdict = probability >= threshold
    preview = f"probability: {probability:.2f}  {bar(probability)}\nverdict: {'yes' if verdict else 'no'} (threshold {threshold:.2f})"
    return NoulResult(probability, verdict, report, preview)


def score(backend: Backend, state: str, instructions: str, levels_text: str) -> ScoreResult:
    levels = parse_levels(levels_text)
    answer, report = _ask(backend, state, score_question(instructions, levels))
    value = float(answer["score"])
    level = min(max(round(value), 0), len(levels) - 1)
    confidence = float(answer["confidence"])
    labels = {str(i): f"{i} {description}" for i, description in enumerate(levels)}
    preview = "\n".join(
        [
            f"score: {value:.2f}",
            f"level: {level} ({levels[level]})",
            f"confidence: {confidence:.2f}",
            "",
            *probability_lines(answer["probabilities"], labels),
        ]
    )
    return ScoreResult(value, level, confidence, report, preview)
