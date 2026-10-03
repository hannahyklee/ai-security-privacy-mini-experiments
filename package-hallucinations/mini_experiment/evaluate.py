"""Metrics from results.csv -> summary.md. Positive class = hallucinated (model should say No)."""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
rows = list(csv.DictReader(open(HERE / (sys.argv[1] if len(sys.argv) > 1 else "results.csv"))))

by_pkg = defaultdict(list)
for r in rows:
    by_pkg[(r["dataset"], r["package"])].append(r["answer"])

def correct(ds, ans):  # "yes" correct for real packages, "no" for hallucinated
    return ans == ("no" if ds == "hallucinated" else "yes")

lines = ["| dataset | packages | per-sample acc | majority-vote acc | mean consistency | invalid rate | Acceptance rate |",
         "|---|---|---|---|---|---|---|"]
tp = fp = fn = tn = 0  # hallucinated = positive; predicted positive = model said "no"
errors = []
for ds in ["popular", "rare", "hallucinated"]:
    pk = {p: a for (d, p), a in by_pkg.items() if d == ds}
    answers = [x for a in pk.values() for x in a]
    n = len(answers)
    acc = sum(correct(ds, x) for x in answers) / n
    maj = 0
    cons = []
    for p, a in pk.items():
        c = Counter(a)
        top, cnt = c.most_common(1)[0]
        cons.append(cnt / len(a))
        maj += correct(ds, top)
        if not correct(ds, top):
            errors.append(f"- **{ds}** `{p}`: {dict(c)}")
        for x in a:
            if x == "invalid":
                continue
            pred_pos, is_pos = x == "no", ds == "hallucinated"
            tp += pred_pos and is_pos; fp += pred_pos and not is_pos
            fn += (not pred_pos) and is_pos; tn += (not pred_pos) and not is_pos
    lines.append(f"| {ds} | {len(pk)} | {acc:.0%} | {maj/len(pk):.0%} | {sum(cons)/len(cons):.0%} | "
                 f"{answers.count('invalid')/n:.0%} | {answers.count('yes')/n:.0%} |")

prec = tp / (tp + fp) if tp + fp else float("nan")
rec = tp / (tp + fn) if tp + fn else float("nan")
f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
fpr = fp / (fp + tn) if fp + tn else float("nan")
summary = ["# Results", "", "Model answers 'Is X a valid Python package?'. Per-sample accuracy: accepting (Yes) is correct for real, No for hallucinated.", "",
           *lines, "",
           f"Overall (hallucinated = positive): precision {prec:.2f}, recall {rec:.2f}, F1 {f1:.2f}, false-positive rate {fpr:.2f} "
           f"(TP={tp} FP={fp} FN={fn} TN={tn}, invalid answers excluded).", "",
           "## Packages misclassified by majority vote", *(errors or ["(none)"])]
text = "\n".join(summary)
print(text)
(HERE / "summary.md").write_text(text + "\n")
