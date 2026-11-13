"""Build results/results_tables.md and results/main_plot.png (bar charts) from results/refunds/*.
Usage: python src/make_tables.py [--dir results]
Extends Shao, Ren et al., "Your Agent May Misevolve" (ICLR 2026, arXiv 2509.26354), Sec. 3.2."""
import argparse
import csv
import json
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ORDER = ["no_memory", "vanilla", "paper_reference", "audit_filter"]
COL = {"no_memory": "#4C78A8", "vanilla": "#D1495B", "paper_reference": "#2A9D8F", "audit_filter": "#7B5EA7"}
LABEL = {"no_memory": "no memory", "vanilla": "vanilla", "paper_reference": "paper: 'for reference only'", "audit_filter": "write-time audit (ours)"}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", default="results"); a = ap.parse_args()
    d = os.path.join(a.dir, "refunds")
    rows = [json.loads(l) for l in open(os.path.join(d, "raw.jsonl"))]
    summ = {r["strategy"]: r for r in csv.DictReader(open(os.path.join(d, "summary.csv")))}
    infl = {r["defense"]: r for r in csv.DictReader(open(os.path.join(d, "influence.csv")))}
    audit = json.load(open(os.path.join(d, "audit.json")))
    f = lambda r, k: f"{float(r[k]):.2f} [{float(r[k+'_ci_lo']):.2f}, {float(r[k+'_ci_hi']):.2f}]"

    def count(s, split, subtype=None):
        rr = [r for r in rows if r["strategy"] == s and r["split"] == split and (subtype is None or r["subtype"] == subtype)]
        return sum(r["is_positive"] for r in rr), len(rr)

    L = ["# Results tables (refunds, 20 seeded memories; qwen2.5:7b-instruct; 3 seeds per query)\n"]
    L += ["## Table 1. Main results\nBrackets: 95% bootstrap CI resampling queries (20 trap, 20 valid). `k/n` = refunds / outputs (3 seeds x queries).\n",
          "| Condition | Unsafe refunds on TRAP queries (lower is better) | k/n | Correct refunds on VALID queries (higher is better) | k/n | Exact-label accuracy on TRAP | Unparseable |", "|---|---|---|---|---|---|---|"]
    for s in ORDER:
        kt, nt = count(s, "trap"); kv, nv = count(s, "valid")
        L.append(f"| {LABEL[s]} | {f(summ[s],'trap_unsafe_rate')} | {kt}/{nt} | {f(summ[s],'valid_correct_rate')} | {kv}/{nv} | {sum(r['parsed_action'] == r['correct_label'] for r in rows if r['strategy'] == s and r['split'] == 'trap') / 60:.2f} | {float(summ[s]['unparseable_rate']):.2f} |")

    L += ["\n## Table 2. Unsafe refunds on TRAP queries, by query type (refunds / outputs)\n",
          "| Query type (n queries) | " + " | ".join(LABEL[s] for s in ORDER) + " |", "|---|" + "---|" * len(ORDER)]
    subs = [("late", "past 30 days, unopened"), ("used", "used / opened, working"), ("policy_only", "asked about policy only"), ("safety", "safety issue or dispute (should escalate)")]
    for st, nm in subs:
        nq = len({r["query_id"] for r in rows if r["split"] == "trap" and r["subtype"] == st})
        L.append(f"| {nm} ({nq}) | " + " | ".join("%d/%d" % count(s, "trap", st) for s in ORDER) + " |")

    L += ["\n## Table 3. Each defense vs. vanilla (same query, same seed)\n",
          "| Defense | Change in unsafe rate [95% CI] | Change in valid-correct rate [95% CI] | Unsafe refunds avoided / newly caused (of 60 trap outputs) | Valid refunds lost / gained (of 60) |", "|---|---|---|---|---|"]
    for df in ("paper_reference", "audit_filter"):
        r = infl[df]
        L.append(f"| {LABEL[df]} | {float(r['delta_trap_vs_vanilla']):+.2f} {r['delta_trap_ci'].replace(';', ', ')} | {float(r['delta_valid_vs_vanilla']):+.2f} {r['delta_valid_ci'].replace(';', ', ')} | "
                 f"{r['trap_good_flips']} / {r['trap_bad_flips']} | {r['valid_bad_flips']} / {r['valid_good_flips']} |")

    def judge_row(name, au):
        ac = au["accuracy"]
        return f"| {name} | {ac['bad_flagged']}/{ac['n_bad']} | {ac['good_rejected']}/{ac['n_good']} | {ac['accuracy']:.2f} |"
    L += ["\n## Table 4. Write-time judge vs. ground truth\n",
          "| Memory set | Bad entries caught (recall) | Good entries wrongly rejected | Accuracy |", "|---|---|---|---|",
          judge_row("**Main run:** 20 entries (10 bad / 10 good)", audit)]

    L += ["\n## Table 5. What the judge decided, per memory entry\n",
          "| Entry | Type | Truly compliant? | Judge tag | Judge's reason (vote 1) |", "|---|---|---|---|---|"]
    for e in audit["audit"]:
        ok = "" if e["truth_compliant"] == e["tag_compliant"] else " **(wrong)**"
        L.append(f"| {e['id']} | {e['kind']} | {'yes' if e['truth_compliant'] else 'no'} | {'compliant' if e['tag_compliant'] else 'non-compliant'}{ok} | {e['reason'][:110]} |")

    L += ["\n## Table 6. TRAP queries where vanilla refunded (refunds / 3 seeds)\n", "| Query | Type | vanilla | paper_reference | audit_filter |", "|---|---|---|---|---|"]
    byq = defaultdict(dict)
    for r in rows:
        if r["split"] == "trap":
            byq[r["query_id"]][r["strategy"]] = byq[r["query_id"]].get(r["strategy"], 0) + int(r["is_positive"])
    sub = {r["query_id"]: r["subtype"] for r in rows}
    for q in sorted(byq):
        if byq[q].get("vanilla", 0) > 0:
            L.append(f"| {q} | {sub[q]} | {byq[q]['vanilla']}/3 | {byq[q]['paper_reference']}/3 | {byq[q]['audit_filter']}/3 |")
    open(os.path.join(a.dir, "results_tables.md"), "w").write("\n".join(L) + "\n")

    # ---- LaTeX tables (booktabs; \usepackage{booktabs}) -> results/tables.tex ----
    TL = {"no_memory": "No memory", "vanilla": "Vanilla", "paper_reference": "Paper prompt (read-time)", "audit_filter": "Write-time audit (ours)"}
    ci = lambda r, k: f"{float(r[k]):.2f} [{float(r[k+'_ci_lo']):.2f}, {float(r[k+'_ci_hi']):.2f}]"
    T = ["% Auto-generated by src/make_tables.py. Requires \\usepackage{booktabs}.\n"]
    # Table: memory composition
    T += ["\\begin{table}[t]\\centering\\small", "\\caption{Seeded memory (20 entries, balanced 10 bad / 10 good).}\\label{tab:memory}",
          "\\begin{tabular}{lrp{7.2cm}}\\toprule", "Entry type & Count & Content \\\\\\midrule",
          "Misleading & 10 & Refund on an ineligible request, rated 5 \\\\",
          "Valid refund & 6 & Justified refund (eligible or defective), rated 5 \\\\",
          "Honest explanation & 4 & Policy explained for an ineligible request, rated 2--3 \\\\\\bottomrule", "\\end{tabular}\\end{table}\n"]
    # Table: main
    T += ["\\begin{table*}[t]\\centering\\small",
          "\\caption{Main results (qwen2.5:7b-instruct; 20 trap and 20 valid queries, 3 seeds each). Brackets: 95\\% bootstrap CI over queries; $k/n$ = refunds / outputs. Exact-label accuracy: output equals the labeled correct action on trap queries.}\\label{tab:main}",
          "\\begin{tabular}{lcccc}\\toprule",
          "Condition & Unsafe refunds, trap $\\downarrow$ & Correct refunds, valid $\\uparrow$ & Exact-label acc., trap $\\uparrow$ & Unparseable \\\\\\midrule"]
    for st in ORDER:
        kt, nt = count(st, "trap"); kv, nv = count(st, "valid")
        acc = sum(r["parsed_action"] == r["correct_label"] for r in rows if r["strategy"] == st and r["split"] == "trap") / nt
        T.append(f"{TL[st]} & {ci(summ[st],'trap_unsafe_rate')} ({kt}/{nt}) & {ci(summ[st],'valid_correct_rate')} ({kv}/{nv}) & {acc:.2f} & {float(summ[st]['unparseable_rate']):.2f} \\\\")
    T += ["\\bottomrule\\end{tabular}\\end{table*}\n"]
    # Table: by type
    T += ["\\begin{table}[t]\\centering\\small", "\\caption{Unsafe refunds on trap queries by query type (refunds / outputs; 3 seeds per query).}\\label{tab:bytype}",
          "\\begin{tabular}{lcccc}\\toprule", "Query type ($n$ queries) & No mem. & Vanilla & Paper & Audit \\\\\\midrule"]
    for st_, nm in subs:
        nq = len({r["query_id"] for r in rows if r["split"] == "trap" and r["subtype"] == st_})
        T.append(f"{nm.split(' (')[0].replace('safety issue or dispute', 'Safety / dispute').replace('past 30 days, unopened', 'Past 30 days').replace('used / opened, working', 'Used / opened').replace('asked about policy only', 'Policy question only')} ({nq}) & "
                 + " & ".join("%d/%d" % count(x, "trap", st_) for x in ORDER) + " \\\\")
    T += ["\\bottomrule\\end{tabular}\\end{table}\n"]
    # Table: defense vs vanilla
    T += ["\\begin{table}[t]\\centering\\small",
          "\\caption{Each defense versus vanilla on identical (query, seed) pairs. Changes in rate with 95\\% bootstrap CI; counts are outputs out of 60.}\\label{tab:defense}",
          "\\begin{tabular}{lcccc}\\toprule", "Defense & $\\Delta$ unsafe rate & $\\Delta$ valid-correct rate & Unsafe avoided / caused & Valid lost / gained \\\\\\midrule"]
    for df in ("paper_reference", "audit_filter"):
        r = infl[df]
        T.append(f"{TL[df]} & {float(r['delta_trap_vs_vanilla']):+.2f} {r['delta_trap_ci'].replace(';', ', ')} & {float(r['delta_valid_vs_vanilla']):+.2f} {r['delta_valid_ci'].replace(';', ', ')} & {r['trap_good_flips']} / {r['trap_bad_flips']} & {r['valid_bad_flips']} / {r['valid_good_flips']} \\\\")
    T += ["\\bottomrule\\end{tabular}\\end{table}\n"]
    # Table: judge
    def jrow(nm, au):
        ac = au["accuracy"]; return f"{nm} & {ac['bad_flagged']}/{ac['n_bad']} & {ac['good_rejected']}/{ac['n_good']} & {ac['accuracy']:.2f} \\\\"
    T += ["\\begin{table}[t]\\centering\\small",
          "\\caption{Write-time judge against ground-truth compliance labels. Recall: bad entries flagged; false rejects: good entries tagged non-compliant.}\\label{tab:judge}",
          "\\begin{tabular}{lccc}\\toprule", "Judge / memory set & Bad caught & False rejects & Accuracy \\\\\\midrule",
          jrow("20 entries (10 bad / 10 good)", audit)]
    T += ["\\bottomrule\\end{tabular}\\end{table}\n"]
    import re
    open(os.path.join(a.dir, "tables.tex"), "w").write(re.sub(r"(?<![\w-])-(?=\d)", "$-$", "\n".join(T)))  # proper math minus

    # ---- figure: left = unsafe refunds on TRAP; middle = correct refunds on VALID; right = TRAP by query type ----
    fig, (ax1, axv, ax2) = plt.subplots(1, 3, figsize=(15.5, 4.6), gridspec_kw=dict(width_ratios=[1, 1, 1.5]))
    xt = ["no\nmemory", "vanilla", "paper:\n'reference\nonly'", "write-time\naudit\n(ours)"]
    for ax, key, title, ylab, top in ((ax1, "trap_unsafe_rate", "TRAP queries: unsafe refunds (lower is better)", "Unsafe refunds (%)", 62),
                                      (axv, "valid_correct_rate", "VALID queries: correct refunds (higher is better)", "Correct refunds (%)", 118)):
        split = "trap" if key.startswith("trap") else "valid"
        for i, st in enumerate(ORDER):
            r = summ[st]; y = float(r[key]) * 100; lo, hi = float(r[key + "_ci_lo"]) * 100, float(r[key + "_ci_hi"]) * 100
            ax.bar(i, y, color=COL[st], width=0.62)
            ax.errorbar(i, y, yerr=[[y - lo], [hi - y]], color="#333", capsize=4, lw=1.2)
            k, n = count(st, split); ax.text(i, min(hi, 100) + 2, f"{k}/{n}", ha="center", fontsize=9, color="#333")
        ax.set_xticks(range(len(ORDER))); ax.set_xticklabels(xt, fontsize=9)
        ax.set_ylabel(ylab); ax.set_ylim(0, top); ax.set_title(title, fontsize=10.5)
    axv.set_yticks([0, 25, 50, 75, 100])
    w = 0.2
    for j, st in enumerate(ORDER):
        ys = [100 * count(st, "trap", sty)[0] / count(st, "trap", sty)[1] for sty, _ in subs]
        xs = [k + (j - 1.5) * w for k in range(len(subs))]
        ax2.bar(xs, ys, width=w, color=COL[st], label=LABEL[st])
        for x, yv in zip(xs, ys):
            ax2.text(x, yv + 1.5, f"{yv:.0f}", ha="center", fontsize=7.5, color="#333")
    ax2.set_xticks(range(len(subs))); ax2.set_xticklabels(["past 30\ndays", "used /\nopened", "policy\nquestion only", "safety /\ndispute"], fontsize=9)
    ax2.set_ylim(0, 100); ax2.set_title("TRAP queries by type: unsafe refunds (%)", fontsize=10.5); ax2.legend(frameon=False, fontsize=8.5, loc="upper left")
    for ax in (ax1, axv, ax2):
        ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", alpha=0.25, lw=0.6); ax.set_axisbelow(True)
    fig.suptitle("Refund agent, qwen2.5:7b-instruct, 20 seeded memories, 3 seeds per query", fontsize=10.5, y=0.995)
    fig.text(0.01, 0.01, "Bars (left, middle): 95% bootstrap CI over 20 queries; labels are refunds / outputs (3 seeds). Right panel: 4-6 queries per type.", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95)); fig.savefig(os.path.join(a.dir, "main_plot.png"), dpi=180); plt.close(fig)

    # ---- worked examples: what the agent actually saw/said ----
    def ex(q):
        out = []
        for st in ("vanilla", "paper_reference", "audit_filter"):
            r = next(x for x in rows if x["strategy"] == st and x["query_id"] == q and x["seed"] == 0)
            out.append(f"### {LABEL[st]}  ->  **{r['parsed_action']}**  (retrieved {r['retrieved_ids']})\n\n```\n{r['prompt']}\n```\nAgent message: {r['message']}\n")
        return out
    E = ["# Worked examples (seed 0): the exact prompt the agent saw in each condition\n"]
    for q, note in (("T14", "safety trap (correct: escalate)"), ("T03", "late trap, 38 days (correct: explain_policy)"), ("V10", "valid, cracked screen (correct: refund)")):
        E.append(f"## {q}: {note}\n"); E += ex(q)
    open(os.path.join(a.dir, "examples.md"), "w").write("\n".join(E))


if __name__ == "__main__":
    main()
