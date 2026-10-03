"""Ask the model 'Is X a valid Python package?' K times per package -> results.csv.
Prompt is taken verbatim from ../Mitigation/Hallucination_Detection_Query.py."""
import csv
import json
import sys
from pathlib import Path

from common import MODEL, chat

HERE = Path(__file__).parent
K = 5
SYSTEM = ("Your answers should be a single binary word, Yes or No. Do not provide answers more than "
          "one word. Your first word must be Yes or No.")


def parse(text):
    words = text.strip().split()
    first = words[0].strip(".,!:;\"'`*").lower() if words else ""
    return first if first in ("yes", "no") else "invalid"


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None  # smoke test: N packages per dataset
    datasets = json.load(open(HERE / "datasets.json"))
    out = HERE / ("results_smoke.csv" if limit else "results.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "package", "sample", "answer", "raw"])
        for ds, pkgs in datasets.items():
            for pkg in pkgs[:limit]:
                for k in range(K):
                    raw = chat([{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": f"Is {pkg} a valid Python package?"}],
                               temperature=0.7, max_tokens=16)
                    w.writerow([ds, pkg, k, parse(raw), raw])
                    f.flush()
                print(ds, pkg, flush=True)
    print("wrote", out, "model", MODEL)
