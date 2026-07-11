"""Minimal OpenAI-compatible chat client for DashScope (Bailian), stdlib only."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


def load_env(root: str) -> dict:
    env = {}
    path = os.path.join(root, ".env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k] = v
    env.setdefault("TONGYI_API_KEY", os.environ.get("TONGYI_API_KEY", ""))
    env.setdefault("DASHSCOPE_BASE_URL",
                   os.environ.get("DASHSCOPE_BASE_URL",
                                  "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    env.setdefault("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
    env.setdefault("OPENROUTER_BASE_URL",
                   os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    return env


def resolve_provider(model: str, env: dict) -> tuple[str, str]:
    """Route a model id to (api_key, base_url). OpenRouter ids look like
    'vendor/model' (e.g. openai/gpt-5.6-sol); everything else goes to Bailian."""
    if "/" in model:
        return env["OPENROUTER_API_KEY"], env["OPENROUTER_BASE_URL"]
    return env["TONGYI_API_KEY"], env["DASHSCOPE_BASE_URL"]


class LLMClient:
    def __init__(self, model: str, api_key: str, base_url: str,
                 temperature: float = 0.4, max_tokens: int = 4000):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.calls = 0
        self.errors = 0

    def chat(self, messages: list[dict], max_retries: int = 5) -> str:
        payload = dict(model=self.model, messages=messages,
                       temperature=self.temperature, max_tokens=self.max_tokens)
        last_err = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    self.base_url + "/chat/completions",
                    data=json.dumps(payload).encode(),
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=300) as resp:
                    out = json.loads(resp.read().decode())
                usage = out.get("usage") or {}
                self.total_prompt_tokens += usage.get("prompt_tokens", 0)
                self.total_completion_tokens += usage.get("completion_tokens", 0)
                self.calls += 1
                msg = out["choices"][0]["message"]
                content = msg.get("content") or ""
                # some reasoning models put nothing in content on truncation
                if not content and msg.get("reasoning_content"):
                    content = ""
                return content
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode()[:300]
                except Exception:
                    pass
                last_err = f"HTTP {e.code}: {body}"
                if e.code in (400, 401, 404):
                    break  # non-retryable
                time.sleep(min(60, 2 ** attempt * 3))
            except Exception as e:  # timeouts, connection resets
                last_err = repr(e)
                time.sleep(min(60, 2 ** attempt * 3))
        self.errors += 1
        raise RuntimeError(f"LLM call failed after retries: {last_err}")

    def usage(self) -> dict:
        return dict(model=self.model, calls=self.calls, errors=self.errors,
                    prompt_tokens=self.total_prompt_tokens,
                    completion_tokens=self.total_completion_tokens)
