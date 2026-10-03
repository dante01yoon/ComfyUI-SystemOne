import base64
import io
import json
import urllib.error
import urllib.request

import pytest

from systemone.backends import CLEF_IMAGE_BUDGET_BYTES, ClefBackend, JevBackend, LayaBackend, build_backend, fit_images

QUESTIONS = {"q": {"type": "noul", "instructions": "Is it night?"}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_jev_posts_state_model_and_questions_with_bearer_key(monkeypatch):
    sent = {}

    def urlopen(request, timeout):
        sent.update(request=request, timeout=timeout)
        return FakeResponse(json.dumps({"model": "jev-1.13.0", "answers": {"q": {"noul": 0.7}}, "usage": {}}).encode())

    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    answers = JevBackend("jev-1.13.0").ask({"time": "23:00"}, QUESTIONS)

    request = sent["request"]
    assert answers == {"q": {"noul": 0.7}}
    assert (request.full_url, request.get_method(), sent["timeout"]) == ("https://api.typesafe.ai/v1/systemone", "POST", 30)
    assert request.get_header("Authorization") == "Bearer sk-test"
    assert json.loads(request.data) == {"state": {"time": "23:00"}, "model": "jev-1.13.0", "questions": QUESTIONS}


def test_jev_without_key_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network call without key"))
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        JevBackend("jev-1.13.0").ask("s", QUESTIONS)


def test_jev_http_error_reports_status_and_body_but_not_key(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}'))

    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-secret")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match=r'HTTP 401: \{"error":"bad key"\}') as error:
        JevBackend("jev-1.13.0").ask("s", QUESTIONS)
    assert "sk-secret" not in str(error.value)


@pytest.mark.parametrize(
    ("widgets", "expected"),
    [
        (("laya", "convaiinnovations/laya", "auto", "x"), LayaBackend("convaiinnovations/laya", None, None)),
        (("laya", "convaiinnovations/laya (multilingual)", "mps", "x"), LayaBackend("convaiinnovations/laya", "multilingual", "mps")),
        (("jev", "convaiinnovations/laya", "cpu", " "), JevBackend("jev-1.13.0")),
        (("jev", "convaiinnovations/laya", "cpu", "jev-2"), JevBackend("jev-2")),
        (("clef-flash", "convaiinnovations/laya", "cpu", "jev-2"), ClefBackend("clef-flash")),
        (("clef", "convaiinnovations/laya", "auto", ""), ClefBackend("clef")),
    ],
)
def test_build_backend_from_widgets(widgets, expected):
    assert build_backend(*widgets) == expected


ANSWERS = {"q": {"noul": 0.3}}


def capture_urlopen(monkeypatch, payload):
    sent = {}

    def urlopen(request, timeout):
        sent.update(request=request, timeout=timeout)
        return FakeResponse(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return sent


@pytest.fixture
def cloudflare_env(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-secret")


@pytest.mark.parametrize(
    ("images", "expected_images"),
    [
        (None, None),
        ([], None),
        (
            [lambda side: b"jpeg-a", lambda side: b"jpeg-b"],
            [f"data:image/jpeg;base64,{base64.b64encode(b'jpeg-a').decode()}", f"data:image/jpeg;base64,{base64.b64encode(b'jpeg-b').decode()}"],
        ),
    ],
)
def test_clef_request_shape(monkeypatch, cloudflare_env, images, expected_images):
    sent = capture_urlopen(monkeypatch, {"answers": ANSWERS})

    assert ClefBackend("clef-flash").ask({"prompt": "a cat"}, QUESTIONS, images) == ANSWERS

    request = sent["request"]
    assert request.full_url == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/cloudflare/clef-flash"
    assert (request.get_method(), sent["timeout"]) == ("POST", 60)
    assert request.get_header("Authorization") == "Bearer cf-secret"
    expected = {"model": "clef-flash", "state": {"prompt": "a cat"}, "questions": QUESTIONS}
    if expected_images is not None:
        expected["images"] = expected_images
    assert json.loads(request.data) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"answers": ANSWERS},
        {"result": {"answers": ANSWERS}, "success": True, "errors": []},
    ],
)
def test_clef_unwraps_result_envelope(monkeypatch, cloudflare_env, payload):
    capture_urlopen(monkeypatch, payload)
    assert ClefBackend("clef").ask("s", QUESTIONS) == ANSWERS


def test_clef_reports_errors_when_success_is_false(monkeypatch, cloudflare_env):
    capture_urlopen(monkeypatch, {"result": None, "success": False, "errors": [{"code": 5006, "message": "bad image"}]})
    with pytest.raises(RuntimeError, match="bad image"):
        ClefBackend("clef").ask("s", QUESTIONS)


def test_clef_http_error_reports_status_and_body_but_not_token(monkeypatch, cloudflare_env):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"errors":["too big"]}'))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match=r"Clef API returned HTTP 400: .*too big") as error:
        ClefBackend("clef").ask("s", QUESTIONS, [lambda side: b"img"])
    assert "cf-secret" not in str(error.value)


@pytest.mark.parametrize("missing", ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"])
def test_clef_missing_env_var_is_named_before_any_request(monkeypatch, cloudflare_env, missing):
    monkeypatch.delenv(missing)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network call without credentials"))
    with pytest.raises(RuntimeError, match=missing):
        ClefBackend("clef").ask("s", QUESTIONS)


def test_clef_rejects_more_than_four_images_before_any_request(monkeypatch, cloudflare_env):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network call with too many images"))
    with pytest.raises(RuntimeError, match="at most 4 images"):
        ClefBackend("clef").ask("s", QUESTIONS, [lambda side: b"img"] * 5)


@pytest.mark.parametrize(
    "backend",
    [LayaBackend("convaiinnovations/laya", None, None), JevBackend("jev-1.13.0")],
)
def test_text_only_backends_refuse_images(monkeypatch, backend):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network call with images"))
    assert backend.supports_images is False
    with pytest.raises(RuntimeError, match="cannot see images; use a Clef backend"):
        backend.ask("s", QUESTIONS, [lambda side: b"img"])


def square_jpeg(bytes_per_pixel_side):
    return lambda long_side: b"x" * (long_side * bytes_per_pixel_side)


@pytest.mark.parametrize(
    ("count", "bytes_per_side", "expected_side"),
    [
        (1, 100, 512),
        (4, 70, 512),
        (4, 100, 320),
        (4, 140, 256),
    ],
)
def test_fit_images_steps_down_until_the_call_fits_the_budget(count, bytes_per_side, expected_side):
    encoded = fit_images([square_jpeg(bytes_per_side)] * count)
    assert [len(blob) for blob in encoded] == [expected_side * bytes_per_side] * count
    assert sum(len(blob) for blob in encoded) <= CLEF_IMAGE_BUDGET_BYTES


def test_fit_images_fails_when_even_the_smallest_side_is_over_budget():
    with pytest.raises(RuntimeError, match="budget"):
        fit_images([square_jpeg(200)] * 4)
