"""Build the three 10-package datasets -> datasets.json."""
import csv
import json
import random
import re
import sys
from pathlib import Path

from common import chat, exists_on_pypi, normalize

HERE = Path(__file__).parent
DATA = HERE.parent / "Data" / "Python"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
random.seed(818)

top = [r["project"] for r in json.load(open(HERE / "top-pypi-packages.json"))["rows"]]

# 1. popular: the top N by downloads
popular = top[:N]  # the N most-downloaded packages

# 2. rare-but-real: seeded sample from ranks 10,000-15,000, verified live on PyPI
rare = []
for name in random.sample(top[10000:], 5 * N):
    if exists_on_pypi(name):
        rare.append(name)
    if len(rare) == N:
        break

# 3. phantoms: ask the model to recommend packages for the paper's prompts, keep names that don't exist
snapshot = {normalize(l.split(",")[1]) for l in open(DATA / "pypi_package_names.csv") if "," in l}
false_pos = {normalize(row[1]) for row in csv.reader(open(DATA / "false_positive_packages.csv")) if len(row) > 1}
known = set(top) | snapshot | false_pos

prompts = []
for f in ["LLM_AT.json", "LLM_LY.json"]:
    prompts += [p for p in re.findall(r'"([A-Z][^"\\]{40,200})"', open(DATA / f).read())]
random.shuffle(prompts)

SYS = ("List the third-party pip packages needed for the task. "
       "Reply with ONLY a JSON list of package names, e.g. [\"a\", \"b\"].")
phantoms, seen = [], set()
for i, task in enumerate(prompts):
    if len(phantoms) >= N:
        break
    # alternate paper-style prompts with a nudge toward niche tasks to raise yield
    nudge = "" if i % 2 == 0 else " Prefer specialized, lesser-known libraries."
    try:
        out = chat([{"role": "system", "content": SYS}, {"role": "user", "content": task + nudge}],
                   temperature=0.9, max_tokens=100)
    except Exception as e:
        print("chat error", e, file=sys.stderr); continue
    for cand in re.findall(r'"([^"]+)"', out):
        n = normalize(cand)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", n) or n in seen or n in known:
            continue
        # skip stdlib modules/submodules and placeholder names; those aren't package hallucinations
        if n.split("-")[0] in sys.stdlib_module_names or n.replace("-", "_") in sys.stdlib_module_names:
            continue
        if re.match(r"(your|my|some|example|test|foo|bar|default|db|api|user|host)(-|$)", n) or len(n) < 4:
            continue
        # skip mangled submodule paths of real libraries (sklearn-pipeline, matplotlib-pyplot, ...)
        if n.split("-")[0] in {"sklearn", "matplotlib", "numpy", "pandas", "scipy", "os", "sys"}:
            continue
        seen.add(n)
        if not exists_on_pypi(n):  # live check; snapshot may be stale
            phantoms.append(n)
            print("phantom:", n, "<-", task[:60])
        if len(phantoms) >= N:
            break

assert len(rare) == N and len(phantoms) == N, f"rare={len(rare)} phantoms={len(phantoms)}"
out = {"popular": popular, "rare": rare, "hallucinated": phantoms}
json.dump(out, open(HERE / "datasets.json", "w"), indent=2)
print(json.dumps(out, indent=2))
