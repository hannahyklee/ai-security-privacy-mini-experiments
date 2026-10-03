"""Tables (txt) + plots (png) from results.csv, datasets.json, top-pypi-packages.json -> out/"""
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import normalize

HERE = Path(__file__).parent
OUT = HERE / "out"
random.seed(0)
ORDER = ["popular", "rare", "hallucinated"]
COLOR = {"popular": "#2a78d6", "rare": "#eb6834", "hallucinated": "#1baf7a"}  # slots 1-3 of the reference palette
INK, MUTED = "#0b0b0b", "#52514e"

# ---- load
ans = defaultdict(list)
for r in csv.DictReader(open(HERE / "results.csv")):
    ans[(r["dataset"], r["package"])].append(r["answer"])
rank = {normalize(r["project"]): (i + 1, r["download_count"])
        for i, r in enumerate(json.load(open(HERE / "top-pypi-packages.json"))["rows"])}
pk = []  # one row per package
for (ds, p), a in ans.items():
    rk, dl = rank.get(normalize(p), (None, None)) if ds != "hallucinated" else (None, 0)
    pk.append(dict(ds=ds, pkg=p, yes=a.count("yes") / len(a), invalid=a.count("invalid") / len(a),
                   rank=rk, dl=dl, n=len(a)))
truth_yes = lambda d: d != "hallucinated"
ok = lambda d, y: (y >= .5) == truth_yes(d)  # majority vote ("yes" if >= half)


def boot_ci(vals, B=2000):
    ms = sorted(statistics.mean(random.choices(vals, k=len(vals))) for _ in range(B))
    return ms[int(.025 * B)], ms[int(.975 * B)]


def tbl(header, rows):
    w = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    f = lambda r: "  ".join(str(x).ljust(w[i]) for i, x in enumerate(r))
    return "\n".join([f(header), "  ".join("-" * x for x in w), *map(f, rows)])


# ---- table 1: by dataset. Headline = one accept/reject decision per package (majority of its 5 answers);
# trial-level mean rate kept as a secondary column.
def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def stats(ds):
    ps = [x for x in pk if x["ds"] == ds]
    n = len(ps)
    acc = sum(x["yes"] > .5 for x in ps)           # packages accepted by majority vote
    unan = sum(x["yes"] in (0, 1) for x in ps)     # packages with 5/5 identical answers
    return dict(n=n, acc=acc, unan=unan, ps=ps,
                cons=statistics.mean(max(x["yes"], 1 - x["yes"]) for x in ps),
                var=statistics.mean(x["yes"] * (1 - x["yes"]) for x in ps))


S = {ds: stats(ds) for ds in ORDER}
rows = []
for ds in ORDER:
    s_ = S[ds]
    lo, hi = wilson(s_["acc"], s_["n"])
    dls = [x["dl"] for x in s_["ps"] if x["dl"]]
    rows.append([ds, s_["n"], f"{s_['acc']/s_['n']:.0%}", f"[{lo:.0%}, {hi:.0%}]",
                 f"{statistics.mean(x['yes'] for x in s_['ps']):.1%}",
                 f"{s_['unan']/s_['n']:.0%}", f"{s_['cons']:.2f}", f"{s_['var']:.3f}",
                 f"{statistics.median(dls):,.0f}" if dls else "n/a (not on PyPI)"])
t1 = tbl(["dataset", "n_pkgs", "accepted(majority)", "95%_CI(Wilson)", "mean_trial_acceptance_rate",
          "unanimous_pkgs", "mean_consistency", "mean_within_pkg_var", "median_30d_downloads"], rows)
t1 += ("\n\naccepted(majority): packages where >= 3 of 5 answers were Yes (one decision per package)."
       "\nunanimous_pkgs: share of packages with 5/5 identical answers. mean_consistency: mean share of a package's"
       "\nanswers agreeing with its majority (0.5-1). mean_within_pkg_var: mean of p(1-p), p = trial acceptance rate (0 = fully consistent).")

# ---- table 2: confusion + classifier metrics (positive = hallucinated = model says No)
tp = fp = fn = tn = 0
for ds in ORDER:
    for a in (a for (d, _), a in ans.items() if d == ds for a in a):
        if a == "invalid":
            continue
        pos, pred = ds == "hallucinated", a == "no"
        tp += pos and pred; fn += pos and not pred; fp += (not pos) and pred; tn += (not pos) and not pred
prec, rec = tp / (tp + fp), tp / (tp + fn)
t2 = (f"Per-sample confusion (positive = hallucinated, predicted positive = model said No)\n"
      + tbl(["", "pred_No(fake)", "pred_Yes(real)"], [["actually hallucinated", tp, fn], ["actually real", fp, tn]])
      + f"\n\nprecision {prec:.3f}  recall {rec:.3f}  F1 {2*prec*rec/(prec+rec):.3f}  FPR {fp/(fp+tn):.3f}  "
        f"accuracy {(tp+tn)/(tp+tn+fp+fn):.3f}")
# real-vs-fake separability: AUC of per-package acceptance rate (real should score higher than hallucinated)
real = [x["yes"] for x in pk if x["ds"] != "hallucinated"]
fake = [x["yes"] for x in pk if x["ds"] == "hallucinated"]
auc = lambda A, B: sum((a > b) + .5 * (a == b) for a in A for b in B) / (len(A) * len(B))
t2 += (f"\n\nAUC (acceptance rate separates real from hallucinated): all real {auc(real, fake):.3f}"
       f" | popular vs hallucinated {auc([x['yes'] for x in pk if x['ds']=='popular'], fake):.3f}"
       f" | rare vs hallucinated {auc([x['yes'] for x in pk if x['ds']=='rare'], fake):.3f}")

# ---- table 3: Acceptance rate by download quintile (real packages only)
realp = sorted((x for x in pk if x["ds"] != "hallucinated"), key=lambda x: -x["dl"])
q = len(realp) // 5
rows, qx, qy = [], [], []
for i in range(5):
    g = realp[i * q:(i + 1) * q]
    ys = [x["yes"] for x in g]
    rows.append([f"Q{i+1}", len(g), f"{max(x['dl'] for x in g):,}", f"{min(x['dl'] for x in g):,}", f"{statistics.mean(ys):.1%}"])
    qx.append(math.exp(statistics.mean(math.log(x["dl"]) for x in g))); qy.append(statistics.mean(ys))
t3 = ("Acceptance rate by download quintile (real packages, popular+rare pooled; Q1 = most downloaded)\n"
      + tbl(["quintile", "n", "max_dl_30d", "min_dl_30d", "mean_acceptance_rate"], rows))
logdl = [math.log10(x["dl"]) for x in realp]
mx, my = statistics.mean(logdl), statistics.mean(x["yes"] for x in realp)
corr = (sum((a - mx) * (x["yes"] - my) for a, x in zip(logdl, realp))
        / math.sqrt(sum((a - mx) ** 2 for a in logdl) * sum((x["yes"] - my) ** 2 for x in realp)))
t3 += f"\n\nPearson r(log10 downloads, acceptance rate) over {len(realp)} real packages: {corr:.3f}"

# ---- table 4: per-package (sorted) + errors
t4 = tbl(["dataset", "package", "rank", "30d_downloads", "acceptance_rate", "correct(majority)"],
         [[x["ds"], x["pkg"], x["rank"] or "-", f"{x['dl']:,}" if x["dl"] else "-", f"{x['yes']:.0%}",
           "yes" if ok(x["ds"], x["yes"]) else "NO"] for ds in ORDER
          for x in sorted((x for x in pk if x["ds"] == ds), key=lambda x: x["yes"])])

for name, t in [("table1_by_dataset", t1), ("table2_confusion_metrics", t2), ("table3_by_download_quintile", t3),
                ("table4_per_package", t4)]:
    (OUT / f"{name}.txt").write_text(t + "\n")
    print(f"== {name}\n{t}\n" if name != "table4_per_package" else f"== {name} (see file)\n")

# ---- plots
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.grid": True, "grid.color": "#e5e5e2", "grid.linewidth": .6, "axes.axisbelow": True})
lbl = {"popular": "Popular", "rare": "Rare", "hallucinated": "Hallucinated"}

# fig 1: share of packages accepted (majority vote of 5 answers), Wilson CI
fig, ax = plt.subplots(figsize=(6, 4))
for i, ds in enumerate(ORDER):
    k, n = S[ds]["acc"], S[ds]["n"]
    m, (lo, hi) = k / n, wilson(k, n)
    ax.bar(i, m, width=.55, color=COLOR[ds], alpha=.6, zorder=2)
    ax.errorbar(i, m, yerr=[[m - lo], [hi - m]], color=INK, capsize=4, lw=1.4, zorder=4)
    ax.text(i, hi + .03, f"{m:.0%}", ha="center", color=INK, fontweight="bold")
ax.set_xticks(range(3), [lbl[d] for d in ORDER]); ax.set_ylim(0, 1.1); ax.set_yticks([0, .25, .5, .75, 1])
ax.set_ylabel("Packages accepted")
ax.set_title("Share of packages accepted as valid", fontsize=10, color=INK, loc="left")
fig.text(.01, .01, "Accepted = majority (>= 3) of 5 answers say valid. n = 100 per dataset.\nWhisker: 95% Wilson CI.", fontsize=7.5, color=MUTED, va="bottom")
fig.tight_layout(rect=(0, .07, 1, 1)); fig.savefig(OUT / "fig1_accepted_by_dataset.png", dpi=170); plt.close(fig)

# fig 4: consistency across the 5 answers, by dataset
fig, ax = plt.subplots(figsize=(6, 4))
for i, ds in enumerate(ORDER):
    k, n = S[ds]["unan"], S[ds]["n"]
    m, (lo, hi) = k / n, wilson(k, n)
    ax.bar(i, m, width=.55, color=COLOR[ds], alpha=.6, zorder=2)
    ax.errorbar(i, m, yerr=[[m - lo], [hi - m]], color=INK, capsize=4, lw=1.4, zorder=4)
    ax.text(i, hi + .03, f"{m:.0%}", ha="center", color=INK, fontweight="bold")
ax.set_xticks(range(3), [lbl[d] for d in ORDER]); ax.set_ylim(0, 1.1); ax.set_yticks([0, .25, .5, .75, 1])
ax.set_ylabel("Packages with 5/5 same answer")
ax.set_title("Answer consistency", fontsize=10, color=INK, loc="left")
fig.text(.01, .01, "Share of packages whose 5 answers all agree. Whisker: 95% Wilson CI.", fontsize=7.5, color=MUTED, va="bottom")
fig.tight_layout(rect=(0, .05, 1, 1)); fig.savefig(OUT / "fig4_consistency_by_dataset.png", dpi=170); plt.close(fig)

# fig 2: acceptance rate vs log downloads (real) with a separate broken-axis panel for hallucinated (0 downloads)
fig, (ax0, ax) = plt.subplots(1, 2, sharey=True, figsize=(7.6, 4.4), gridspec_kw={"width_ratios": [1, 6], "wspace": .06})
g = [x for x in pk if x["ds"] == "hallucinated"]
ax0.scatter([random.uniform(-.3, .3) for _ in g], [x["yes"] + random.uniform(-.015, .015) for x in g], s=22,
            color=COLOR["hallucinated"], marker="s", edgecolor="white", lw=.4, zorder=3)
ax0.set_xlim(-.6, .6); ax0.set_xticks([0], ["0"]); ax0.grid(axis="x", visible=False)
ax0.spines["right"].set_visible(False)
ax0.set_ylabel("Acceptance rate")
for ds in ("popular", "rare"):
    g = [x for x in pk if x["ds"] == ds]
    ax.scatter([x["dl"] for x in g], [x["yes"] + random.uniform(-.015, .015) for x in g], s=22, color=COLOR[ds],
               edgecolor="white", lw=.4, zorder=3)
ax.set_xscale("log"); ax.set_xlim(3e4, 4e9); ax.set_ylim(-.05, 1.08)
ax.tick_params(left=False); ax.spines["left"].set_visible(False)
ax.set_xlabel("30-day downloads (log)")
ax.text(7.5e4, .31, "Rare", color=INK, ha="center", fontsize=9)
ax0.text(0, .31, "Halluc.", color=INK, ha="center", fontsize=9)
ax.text(5e8, .31, "Popular", color=INK, ha="center", fontsize=9)
fig.suptitle("Acceptance rate vs. downloads", fontsize=10, color=INK, x=.02, ha="left")
fig.subplots_adjust(left=.1, right=.98, top=.9, bottom=.17); fig.savefig(OUT / "fig2_yes_rate_vs_downloads.png", dpi=170); plt.close(fig)

# fig 3: distribution of per-package acceptance rate (histogram, 6 possible values 0,.2,...,1)
fig, ax = plt.subplots(figsize=(7, 4))
vals = [0, .2, .4, .6, .8, 1.0]; w = .26
for j, ds in enumerate(ORDER):
    c = Counter(round(x["yes"], 1) for x in pk if x["ds"] == ds)
    ax.bar([k + (j - 1) * (w + .02) for k in range(6)], [c[round(v, 1)] for v in vals], width=w, color=COLOR[ds],
           label=lbl[ds], zorder=3)
ax.set_xticks(range(6), [f"{int(v*5)}/5" for v in vals]); ax.set_xlabel("Acceptances (of 5 samples)")
ax.set_ylabel("Packages"); ax.legend(frameon=False, fontsize=8)
ax.set_title("Acceptances per package", fontsize=10, color=INK, loc="left")
fig.tight_layout(); fig.savefig(OUT / "fig3_answer_distribution.png", dpi=170); plt.close(fig)
print("wrote", sorted(p.name for p in OUT.iterdir()))
