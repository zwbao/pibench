"""Probe the DashScope OpenAI-compatible endpoint: list models, test chat on candidates."""
import os, sys, json, time
import urllib.request

def load_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = load_env(os.path.join(ROOT, ".env"))
KEY = ENV["TONGYI_API_KEY"]
BASE = ENV["DASHSCOPE_BASE_URL"]

def req(path, payload=None, timeout=60):
    url = BASE + path
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

# 1. List models
try:
    models = req("/models")
    ids = sorted(m["id"] for m in models.get("data", []))
    print(f"MODELS AVAILABLE ({len(ids)}):")
    for i in ids:
        print("  ", i)
except Exception as e:
    print("model list failed:", e)

# 2. Chat test on candidates
candidates = sys.argv[1:] or ["qwen3-max", "qwen-max", "qwen-plus", "qwen-turbo",
                              "deepseek-v3.2", "deepseek-v3.1", "deepseek-v3", "deepseek-r1",
                              "kimi-k2-instruct", "glm-4.7", "qwen3-coder-plus"]
for m in candidates:
    t0 = time.time()
    try:
        out = req("/chat/completions", {
            "model": m,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 512,
        }, timeout=90)
        msg = out["choices"][0]["message"]["content"].strip().replace("\n", " ")[:60]
        usage = out.get("usage", {})
        print(f"CHAT {m:24s} ok  {time.time()-t0:5.1f}s  '{msg}'  tokens={usage.get('total_tokens')}")
    except Exception as e:
        err = str(e)
        try:
            import urllib.error
            if isinstance(e, urllib.error.HTTPError):
                err = f"{e.code} {e.read().decode()[:120]}"
        except Exception:
            pass
        print(f"CHAT {m:24s} FAIL {time.time()-t0:5.1f}s  {err[:160]}")
