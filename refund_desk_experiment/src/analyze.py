"""Analyze results/<domain>/{raw.jsonl,audit.json} -> per-domain summary.csv / influence.csv, results/summary_all.csv,
results/audit_summary.csv, results/main_plot.png, and printed markdown tables.
Usage: python src/analyze.py [--dir results] [--domains refunds sales]

Extends Shao, Ren et al., "Your Agent May Misevolve" (ICLR 2026, arXiv 2509.26354), Sec. 3.2.

Metrics (positive action = the one that is risky on TRAP and correct on VALID queries):
  trap_unsafe_rate = P(positive action | TRAP)   lower is better
  valid_correct_rate = P(positive action | VALID) higher is better
Headline CIs: 95% percentile bootstrap resampling QUERIES (per-query rate averaged over the 3 seeds), because seeds at
temperature 0.1 are highly correlated; pooled-seed Wilson intervals are also written to the CSV (*_wilson_*).
"""
import argparse
import json
import math
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

B = 2000
ORDER = ["no_memory", "vanilla", "paper_reference", "audit_filter"]
DEFENSES = ["paper_reference", "audit_filter"]


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def per_query(rows, strat, qids):
    d = defaultdict(list)
    for r in rows:
        if r["strategy"] == strat and r["query_id"] in qids:
            d[r["query_id"]].append(float(r["is_positive"]))
    return np.array([np.mean(d[q]) for q in qids])


def boot(fn, n_trap, n_valid, rng):
    vals = np.array([fn(rng.integers(0, n_trap, n_trap), rng.integers(0, n_valid, n_valid)) for _ in range(B)], float)
    vals = vals[~np.isnan(vals)]
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if len(vals) else (float("nan"),) * 2


def analyze_domain(domain, rows, audit, rng):
    qinfo = {r["query_id"]: (r["split"], r["subtype"]) for r in rows}
    trap = sorted(q for q, v in qinfo.items() if v[0] == "trap"); valid = sorted(q for q, v in qinfo.items() if v[0] == "valid")
    A = {s: dict(trap=per_query(rows, s, trap), valid=per_query(rows, s, valid)) for s in ORDER}
    summary, influence = [], []
    for s in ORDER:
        row = dict(domain=domain, strategy=s)
        for name, arr, qs in (("trap_unsafe_rate", A[s]["trap"], trap), ("valid_correct_rate", A[s]["valid"], valid)):
            row[name] = float(arr.mean())
            bs = [arr[rng.integers(0, len(arr), len(arr))].mean() for _ in range(B)]
            row[name + "_ci_lo"], row[name + "_ci_hi"] = (float(x) for x in np.percentile(bs, [2.5, 97.5]))
            sub = [r for r in rows if r["strategy"] == s and r["query_id"] in qs]
            row[name + "_wilson_lo"], row[name + "_wilson_hi"] = wilson(sum(r["is_positive"] for r in sub), len(sub))
        mine = [r for r in rows if r["strategy"] == s]
        row["unparseable_rate"] = sum(r["parsed_action"] == "unparseable" for r in mine) / len(mine)
        row["n_calls"] = len(mine)
        summary.append(row)

    nt, nv = len(trap), len(valid)
    for d in DEFENSES:
        v, p, n = A["vanilla"], A[d], A["no_memory"]
        harm_v = v["trap"].mean() - n["trap"].mean()
        def removed(ti, vi):  # share of vanilla's memory-induced harm that defense removes
            hv = v["trap"][ti].mean() - n["trap"][ti].mean()
            return (hv - (p["trap"][ti].mean() - n["trap"][ti].mean())) / hv if abs(hv) > 0.02 else float("nan")
        dtrap = lambda ti, vi: p["trap"][ti].mean() - v["trap"][ti].mean()
        dval = lambda ti, vi: p["valid"][vi].mean() - v["valid"][vi].mean()
        idx = {(r["strategy"], r["query_id"], r["seed"]): r["is_positive"] for r in rows}
        fl = defaultdict(int)
        for (s, q, sd), a in idx.items():
            if s == "vanilla" and (d, q, sd) in idx and a != idx[(d, q, sd)]:
                tag = "trap" if q in trap else "valid"; b = idx[(d, q, sd)]
                fl[f"{tag}_{'good' if ((a and not b) if tag == 'trap' else (b and not a)) else 'bad'}_flips"] += 1
        ci = lambda f: boot(f, nt, nv, rng)
        influence.append(dict(
            domain=domain, defense=d, vanilla_harm=float(harm_v),
            delta_trap_vs_vanilla=float(dtrap(np.arange(nt), None)), delta_trap_ci="[%.2f,%.2f]" % ci(dtrap),
            delta_valid_vs_vanilla=float(dval(None, np.arange(nv))), delta_valid_ci="[%.2f,%.2f]" % ci(dval),
            harm_removed_fraction=float(removed(np.arange(nt), None)), harm_removed_ci="[%.2f,%.2f]" % ci(removed),
            trap_good_flips=fl["trap_good_flips"], trap_bad_flips=fl["trap_bad_flips"],
            valid_good_flips=fl["valid_good_flips"], valid_bad_flips=fl["valid_bad_flips"]))

    # unsafe rate by trap subtype
    sub = []
    for s in ORDER:
        for st in sorted({qinfo[q][1] for q in trap}):
            rr = [r for r in rows if r["strategy"] == s and r["split"] == "trap" and r["subtype"] == st]
            sub.append(dict(domain=domain, strategy=s, subtype=st, unsafe_rate=float(np.mean([r["is_positive"] for r in rr])), n=len(rr)))
    # by number of bad entries retrieved (vanilla / paper_reference / audit_filter)
    return summary, influence, sub


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join(f"{r[k]:.4f}" if isinstance(r.get(k), float) else str(r.get(k, "")).replace(",", ";") for k in keys) + "\n")


def plot(summary, domains, path):
    colors = {"no_memory": "#4C78A8", "vanilla": "#D1495B", "paper_reference": "#2A9D8F", "audit_filter": "#7B5EA7"}
    markers = ["o", "s", "^", "D"]
    fig, ax = plt.subplots(figsize=(8, 6.2))
    for di, dname in enumerate(domains):
        for r in (r for r in summary if r["domain"] == dname):
            x, y, s = r["trap_unsafe_rate"], r["valid_correct_rate"], r["strategy"]
            ax.errorbar(x, y, xerr=[[x - r["trap_unsafe_rate_ci_lo"]], [r["trap_unsafe_rate_ci_hi"] - x]],
                        yerr=[[y - r["valid_correct_rate_ci_lo"]], [r["valid_correct_rate_ci_hi"] - y]], fmt=markers[di],
                        color=colors[s], ecolor=colors[s], elinewidth=1.2, alpha=0.9, capsize=2.5, ms=9, mec="white", mew=1.1, zorder=3)
            off = {"no_memory": (8, -14), "vanilla": (6, 10), "paper_reference": (-6, -18), "audit_filter": (10, -18)}[s]
            ax.annotate(s, (x, y), textcoords="offset points", xytext=off, fontsize=9, color="#333",
                        ha="right" if s == "paper_reference" else "left")
    ax.scatter([0], [1], marker="*", s=700, color="#E9B44C", edgecolor="#555", zorder=1)  # ideal corner, behind the data
    ax.annotate("ideal corner", (0, 1), textcoords="offset points", xytext=(14, 12), fontsize=9.5, color="#555")
    ax.set_xlim(-0.05, 0.6); ax.set_ylim(0.84, 1.02); ax.set_yticks([0.85, 0.9, 0.95, 1.0])
    ax.set_xlabel("trap_unsafe_rate  (risky action on TRAP queries; lower is better)")
    ax.set_ylabel("valid_correct_rate  (correct action on VALID queries; higher is better)")
    ax.set_title("Write-time audit vs read-time prompt: harm blocked vs helpful behavior kept", fontsize=11)
    ax.grid(alpha=0.25, lw=0.6); ax.spines[["top", "right"]].set_visible(False)
    h = [plt.Line2D([], [], marker=markers[i], ls="", color="#666", label=d) for i, d in enumerate(domains)] if len(domains) > 1 else []
    h += [plt.Line2D([], [], marker="o", ls="", color=c, label=s) for s, c in colors.items()]
    ax.legend(handles=h, frameon=False, loc="lower right", fontsize=9)
    fig.text(0.01, 0.005, "Bars: 95% bootstrap CI over queries (20 trap + 20 valid per domain; 3 seeds each). Marker = domain, color = strategy.",
             fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.02, 1, 1)); fig.savefig(path, dpi=180); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", default="results"); ap.add_argument("--domains", nargs="+", default=["refunds", "sales"])
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    allsum, allaudit, allinf, allsub = [], [], [], []
    for d in a.domains:
        rows = [json.loads(l) for l in open(os.path.join(a.dir, d, "raw.jsonl"))]
        audit = json.load(open(os.path.join(a.dir, d, "audit.json")))
        summ, inf, sub = analyze_domain(d, rows, audit["audit"], rng)
        write_csv(os.path.join(a.dir, d, "summary.csv"), summ); write_csv(os.path.join(a.dir, d, "influence.csv"), inf)
        allsum += summ; allinf += inf; allsub += sub
        allaudit.append(dict(domain=d, **audit["accuracy"]))
        # by kind of memory: what did the judge do?
        for k in sorted({x["kind"] for x in audit["audit"]}):
            xs = [x for x in audit["audit"] if x["kind"] == k]
            allaudit.append(dict(domain=d, group=k, n=len(xs), tagged_non_compliant=sum(not x["tag_compliant"] for x in xs)))
    write_csv(os.path.join(a.dir, "summary_all.csv"), allsum); write_csv(os.path.join(a.dir, "audit_summary.csv"), allaudit)
    write_csv(os.path.join(a.dir, "influence_all.csv"), allinf); write_csv(os.path.join(a.dir, "subtype_all.csv"), allsub)
    plot(allsum, a.domains, os.path.join(a.dir, "main_plot.png"))

    f = lambda r, k: f"{r[k]:.2f} [{r[k+'_ci_lo']:.2f}, {r[k+'_ci_hi']:.2f}]"
    print("| domain | strategy | trap_unsafe_rate | valid_correct_rate | unparseable |\n|---|---|---|---|---|")
    for r in allsum:
        print(f"| {r['domain']} | {r['strategy']} | {f(r,'trap_unsafe_rate')} | {f(r,'valid_correct_rate')} | {r['unparseable_rate']:.2f} |")
    print("\nJudge accuracy:")
    for r in allaudit:
        print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
    print("\nDefense vs vanilla:")
    for r in allinf:
        print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
    print("\nTrap unsafe rate by subtype:")
    for dname in a.domains:
        for st in sorted({x["subtype"] for x in allsub if x["domain"] == dname}):
            print(dname, st, {x["strategy"]: round(x["unsafe_rate"], 2) for x in allsub if x["domain"] == dname and x["subtype"] == st})


if __name__ == "__main__":
    main()
