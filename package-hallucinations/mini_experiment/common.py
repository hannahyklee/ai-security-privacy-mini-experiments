"""Shared helpers: Ollama chat + PyPI existence check (stdlib only)."""
import json
import re
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "qwen2.5-coder:7b"


def normalize(name):
    # same rule as normalize_python in ../package_detection.py
    return re.sub(r"[-_.]+", "-", name).strip(" `.-").lower()


def chat(messages, temperature=0.7, max_tokens=64, model=MODEL):
    body = json.dumps({"model": model, "messages": messages,
                       "temperature": temperature, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(OLLAMA_URL, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def exists_on_pypi(name):
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=20):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
