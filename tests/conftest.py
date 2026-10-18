import json
import os

import httpx
import pytest
import yaml

from mathfix.config import ROOT, Settings
from mathfix.db import Repo


class InlineSandbox:
    """Runs sandbox functions in-process (fast tests). The real process sandbox has its own test."""

    async def run(self, fn, *args, timeout=2.0):
        return fn(*args)


@pytest.fixture
def models_cfg(monkeypatch):
    for k in ("GROQ_API_KEY", "CF_AI_API_TOKEN", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(k, "test-key")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct")
    return yaml.safe_load((ROOT / "config/models.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def settings(models_cfg, tmp_path):
    return Settings(bot_token="x", mode="polling", webhook_base_url="", webhook_secret="", port=8080,
                    database_path=tmp_path / "t.db", admin_user_ids={999}, admin_chat_id=None, log_level="INFO",
                    models=models_cfg, limits=yaml.safe_load((ROOT / "config/limits.yaml").read_text(encoding="utf-8")))


@pytest.fixture
async def repo(tmp_path):
    r = Repo(tmp_path / "t.db")
    await r.init()
    yield r
    await r.close()


def chat_reply(content, tokens=(100, 50), status=200):
    if isinstance(content, dict):
        content = json.dumps(content)
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}],
                                        "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}})


class FakeAI:
    """httpx transport: answers by model id with queued responses; records calls."""

    def __init__(self):
        self.queues: dict[str, list] = {}
        self.calls: list[dict] = []

    def add(self, model_id, *responses):
        self.queues.setdefault(model_id, []).extend(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append({"url": str(request.url), **body})
        q = self.queues.get(body["model"]) or []
        if not q:
            return httpx.Response(503, json={"error": "no fake response"})
        r = q.pop(0)
        return r if isinstance(r, httpx.Response) else chat_reply(r)

    @property
    def transport(self):
        return httpx.MockTransport(self)

    def models_called(self):
        return [c["model"] for c in self.calls]
