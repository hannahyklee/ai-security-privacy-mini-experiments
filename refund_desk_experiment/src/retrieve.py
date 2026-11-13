"""TF-IDF cosine retrieval over the request text of memory entries, top-k (default 4)."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class Retriever:
    def __init__(self, memory, k=4):
        self.memory, self.k = memory, k
        if memory:
            self.vec = TfidfVectorizer(stop_words="english", sublinear_tf=True)
            self.mat = self.vec.fit_transform([m["query"] for m in memory])

    def __call__(self, text):
        if not self.memory:
            return [], []
        sims = cosine_similarity(self.vec.transform([text]), self.mat)[0]
        order = sorted(range(len(sims)), key=lambda i: (-sims[i], i))[: self.k]  # deterministic ties
        return [self.memory[i] for i in order], [float(sims[i]) for i in order]


def retrieval_check(domain, k=4, verbose=True):
    """Each TRAP query must retrieve >=1 non-compliant (misleading) entry, each VALID query >=1 compliant entry
    whose action is the positive action, so the memory heuristic can actually bite / help."""
    r, ok = Retriever(domain["memory"], k), True
    for q in domain["dev_queries"] + domain["test_queries"]:
        mem, sims = r(q["text"])
        if q["split"] == "trap":
            has = any(not m["compliant"] for m in mem); need = "bad entry"
        else:
            has = any(m["compliant"] and m["action"] == domain["positive_action"] for m in mem); need = "good+pos"
        ok &= has or q["id"] in {d["id"] for d in domain["dev_queries"]}  # dev misses reported, not fatal
        if verbose:
            print(f"{q['id']:5s} {q['split']:5s}/{q['subtype']:13s} need>={need:9s} {'OK ' if has else 'MISS'} "
                  + " ".join(f"{m['id']}({s:.2f})" for m, s in zip(mem, sims)))
    if verbose:
        print("RETRIEVAL CHECK:", "PASS" if ok else "FAIL")
    return ok
