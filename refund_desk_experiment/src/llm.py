"""Swappable model backends behind one function: llm(prompt, seed, system=None) -> raw text.
OllamaLLM talks to a local Ollama server (stdlib HTTP only). MockLLM is a deterministic rule-based stand-in
so the whole pipeline (agent + judge + analysis) can be dry-run with no model.
"""
import json
import random
import re
import urllib.request


class OllamaLLM:
    def __init__(self, model="qwen2.5:7b-instruct", host="http://localhost:11434", temperature=0.1, num_predict=200):
        self.model, self.host, self.temperature, self.num_predict = model, host, temperature, num_predict

    def __call__(self, prompt, seed, system=None):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        payload = dict(model=self.model, stream=False, format="json", messages=msgs,
                       options=dict(temperature=self.temperature, seed=seed, num_predict=self.num_predict))
        req = urllib.request.Request(self.host + "/api/chat", json.dumps(payload).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=300).read())["message"]["content"]

    def info(self):
        tags = json.loads(urllib.request.urlopen(self.host + "/api/tags").read())["models"]
        digest = next((t["digest"] for t in tags if t["name"] == self.model), None)
        ver = json.loads(urllib.request.urlopen(self.host + "/api/version").read())["version"]
        return dict(backend="ollama", model=self.model, digest=digest, ollama_version=ver,
                    temperature=self.temperature, num_predict=self.num_predict)


class MockLLM:
    """Deterministic rule-based fake for dry runs; its numbers are NOT results.
    Agent: domain keyword rule, but copies the highest-rated retrieved action with prob p_copy (lower if the
    'reference only' preamble is present). Judge: compliant iff the entry's action equals the domain rule's action
    for the entry's request, with 10% random flips."""
    def __init__(self, domain, p_copy=0.8, p_copy_reference=0.5, judge_noise=0.1):
        self.rule, self.p_copy, self.p_copy_reference, self.judge_noise = domain["mock_rule"], p_copy, p_copy_reference, judge_noise

    def __call__(self, prompt, seed, system=None):
        rng = random.Random(f"{seed}|{prompt}")
        if "Audit this memory entry." in prompt:
            m = re.search(r'Request: "(.*?)" \| Action taken: (\w+)', prompt, re.S)
            ok = self.rule(m.group(1)) == m.group(2)
            if rng.random() < self.judge_noise:
                ok = not ok
            return json.dumps(dict(compliant=ok, reason="(mock)"))
        req = re.search(r'Current customer request:\n"(.*)"', prompt, re.S).group(1)
        action = self.rule(req)
        mem = re.findall(r"Action taken: (\w+) \| User rating: (\d)/5", prompt)
        if mem:
            best = max(mem, key=lambda x: int(x[1]))[0]
            if rng.random() < (self.p_copy_reference if "for reference only" in prompt else self.p_copy):
                action = best
        return json.dumps(dict(action=action, message="(mock)"))

    def info(self):
        return dict(backend="mock", model="MockLLM", p_copy=self.p_copy, p_copy_reference=self.p_copy_reference,
                    judge_noise=self.judge_noise)


def make_llm(name, domain):
    return MockLLM(domain) if name == "mock" else OllamaLLM(model=name)
