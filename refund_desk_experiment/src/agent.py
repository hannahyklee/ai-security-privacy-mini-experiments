"""Agent: retrieve (from the full or the audited pool) -> build strategy prompt -> llm -> robust parse."""
import json
import re

from retrieve import Retriever
from strategies import STRATEGIES, build_prompt


def parse_action(raw, actions):
    """Return (action | None, message). None => counted as 'unparseable'."""
    obj = None
    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw or "", re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                pass
    if isinstance(obj, dict):
        a = obj.get("action")
        if isinstance(a, str) and a.strip().lower() in actions:
            return a.strip().lower(), str(obj.get("message", ""))
    return None, ""


class Agent:
    def __init__(self, llm, domain, audit=None, k=4):
        self.llm, self.domain = llm, domain
        self.retrievers = {"all": Retriever(domain["memory"], k)}
        if audit is not None:
            ok = {a["id"] for a in audit if a["tag_compliant"]}
            self.retrievers["audited"] = Retriever([m for m in domain["memory"] if m["id"] in ok], k)

    def act(self, strategy, query, seed):
        cfg = STRATEGIES[strategy]
        retrieved = self.retrievers[cfg["pool"]](query["text"])[0] if cfg["memory"] else []
        prompt = build_prompt(strategy, query["text"], retrieved)
        raw = self.llm(prompt, seed, system=self.domain["system_prompt"])
        action, message = parse_action(raw, self.domain["actions"])
        action = action or "unparseable"
        return dict(domain=self.domain["name"], strategy=strategy, query_id=query["id"], split=query["split"],
                    subtype=query["subtype"], seed=seed, retrieved_ids=[m["id"] for m in retrieved],
                    retrieved_kinds=[m["kind"] for m in retrieved], prompt=prompt, raw_output=raw,
                    parsed_action=action, is_positive=action == self.domain["positive_action"], message=message,
                    correct_label=query["label"])
