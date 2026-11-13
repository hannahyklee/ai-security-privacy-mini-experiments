"""Run one domain. Usage (from the project root):
  python src/run_experiment.py --domain refunds --model mock                       # dry run, no model (-> results_mock/)
  python src/run_experiment.py --domain sales --model qwen2.5:7b-instruct --sanity # judge audit + dev sanity only
  python src/run_experiment.py --domain sales --model qwen2.5:7b-instruct          # full run (resumable)
Outputs go to results/<domain>/ : audit.json, raw.jsonl, raw_meta.json.
Extends Shao, Ren et al., "Your Agent May Misevolve" (ICLR 2026, arXiv 2509.26354), Sec. 3.2.
"""
import argparse
import json
import os
import platform
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from agent import Agent
from domains import get_domain
from judge import audit_memory, judge_accuracy
from llm import make_llm
from retrieve import retrieval_check
from strategies import JUDGE_SYSTEM, JUDGE_TEMPLATE, MEMORY_HEADER, ORDER, STRATEGIES

SEEDS = [0, 1, 2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="refunds")
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--out", default="results")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--sanity", action="store_true", help="audit + DEV set only (no_memory, vanilla, audit_filter)")
    args = ap.parse_args()
    random.seed(0); np.random.seed(0)
    dom = get_domain(args.domain)
    out = os.path.join(args.out, args.domain); os.makedirs(out, exist_ok=True)

    print(f"== [{args.domain}] retrieval check =="); assert retrieval_check(dom, args.k), "retrieval check failed"
    llm = make_llm(args.model, dom)

    audit_path = os.path.join(out, "audit.json")
    if os.path.exists(audit_path):
        audit = json.load(open(audit_path))["audit"]
    else:
        audit = audit_memory(llm, dom)
        json.dump(dict(audit=audit, accuracy=judge_accuracy(audit), model=args.model), open(audit_path, "w"), indent=1)
    print("== judge audit =="); print(json.dumps(judge_accuracy(audit)))
    for a in audit:
        flag = "" if a["tag_compliant"] == a["truth_compliant"] else "   <-- judge wrong"
        print(f"  {a['id']:5s} truth_compliant={a['truth_compliant']!s:5s} tagged={a['tag_compliant']!s:5s} votes={a['votes']}{flag}")

    agent = Agent(llm, dom, audit=audit, k=args.k)
    qs = dom["dev_queries"] if args.sanity else dom["test_queries"]
    strategies = ["no_memory", "vanilla", "audit_filter"] if args.sanity else ORDER
    tag = "dev" if args.sanity else "raw"
    raw_path = os.path.join(out, f"{tag}.jsonl")
    done = set()
    if os.path.exists(raw_path):
        for line in open(raw_path):
            r = json.loads(line); done.add((r["strategy"], r["query_id"], r["seed"]))
    json.dump(dict(domain=args.domain, llm=llm.info(), seeds=SEEDS, k=args.k, system_prompt=dom["system_prompt"],
                   policy=dom["policy"], memory_header=MEMORY_HEADER, judge_system=JUDGE_SYSTEM, judge_template=JUDGE_TEMPLATE,
                   strategies={s: STRATEGIES[s] for s in strategies}, memory=dom["memory"], python=platform.python_version(),
                   started=time.strftime("%Y-%m-%d %H:%M:%S")), open(os.path.join(out, f"{tag}_meta.json"), "w"), indent=1)

    total = len(strategies) * len(qs) * len(SEEDS); n = 0; t0 = time.time()
    with open(raw_path, "a") as f:
        for s in strategies:
            for q in qs:
                for seed in SEEDS:
                    n += 1
                    if (s, q["id"], seed) in done:
                        continue
                    row = agent.act(s, q, seed); row["model"] = args.model
                    f.write(json.dumps(row) + "\n"); f.flush()
                    if n % 30 == 0:
                        print(f"{n}/{total}  {time.time()-t0:.0f}s", flush=True)
    rows = [json.loads(l) for l in open(raw_path)]
    print(f"\n== [{args.domain}] {tag}: {len(rows)} rows ==")
    for s in strategies:
        for sp in ("trap", "valid"):
            rr = [r for r in rows if r["strategy"] == s and r["split"] == sp]
            if rr:
                print(f"{s:16s} {sp:5s} positive_rate={np.mean([r['is_positive'] for r in rr]):.2f} "
                      f"unparseable={np.mean([r['parsed_action']=='unparseable' for r in rr]):.2f} n={len(rr)}")


if __name__ == "__main__":
    main()
