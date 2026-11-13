"""Domain registry. A domain = policy + system prompt + labeled seeded memory + labeled test queries."""
import importlib


def _records(rows, split):
    return [dict(id=i, text=t, label=l, subtype=s, split=split) for i, t, l, s in rows]


def get_domain(name):
    d = importlib.import_module(f"domains.{name}").get()
    d["test_queries"] = _records(d["trap"], "trap") + _records(d["valid"], "valid")
    d["dev_queries"] = [dict(id=i, text=t, label=l, subtype=s, split="valid" if l == d["positive_action"] else "trap")
                        for i, t, l, s in d["dev"]]
    return d


DOMAINS = ["refunds", "sales"]
