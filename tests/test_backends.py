import io
import json
import urllib.error
import urllib.request

import pytest

from systemone.backends import JevBackend, LayaBackend, build_backend

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
    ],
)
def test_build_backend_from_widgets(widgets, expected):
    assert build_backend(*widgets) == expected
