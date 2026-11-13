# Write-time memory audit vs. read-time prompting against reward-hacked memories

A small extension of **"Your Agent May Misevolve: Emergent Risks in Self-Evolving LLM Agents"**
(Shao, Ren et al., ICLR 2026, [arXiv 2509.26354](https://arxiv.org/abs/2509.26354)), Sec. 3.2
("deployment-time reward hacking"): agents with memory copy actions that earned high user ratings (e.g. unwarranted
refunds). The paper's only mitigation is a read-time prompt ("memories are for reference only"), evaluated by unsafe
rate alone. The paper's reference code for this section is `Misevolution/memory_misevolution/reward_hacking_test.py`
(hosted API, free-text memory, unlabeled queries). This project is a **loose re-implementation of one scenario** (refunds), using a local Ollama model, structured seeded memory with TF-IDF retrieval, hand-written labeled queries.

**Research question.** Where should an agent defend against reward-hacked memories: at *read time* (the paper's prompt)
or at *write time* (an LLM judge vets each memory against the policy before it can be retrieved)?

## Setup
- **Agent:** refund desk, actions `refund | explain_policy | escalate | other`, JSON mode, short policy in the system prompt
  ([src/domains/refunds.py](src/domains/refunds.py)). Model: `qwen2.5:7b-instruct` (digest `845dbda0ea48`, Ollama 0.40.6),
  temperature 0.1, 3 seeds.
- **Memory (seeded, not evolved):** **20 entries, balanced 10 bad / 10 good**: 10 *misleading* (refund on an ineligible request,
  rating 5), 6 *valid refund* (rating 5), 4 *honest policy explanations* (rating 2-3). Entries: request, action taken, rating, optional note.
  TF-IDF cosine retrieval over the request text, top-k=4. A retrieval check (printed every run) confirms every trap query retrieves
  >=1 misleading entry and every valid query >=1 valid-refund entry.
- **Test sets (hand-written, matched in style/length, labeled; these are *queries*, not memories):** 20 TRAP queries (6 late, 5 used,
  4 policy-question-only, 5 safety/dispute; correct != refund) and 20 VALID queries (15 easy + 5 "hard"; correct = refund).
  Query wording is distinct from every memory entry.
- **Conditions** (prompt text in [src/strategies.py](src/strategies.py)): `no_memory` (control); `vanilla` (retrieved memories, no guidance);
  `paper_reference` (the paper's "for reference only; make an independent decision" preamble); `audit_filter` (**ours**: an LLM judge tags each
  entry compliant / non-compliant at write time; only compliant entries are retrievable; agent prompt identical to vanilla).
- **Judge** ([src/judge.py](src/judge.py)): the *same* 7B model. It sees the policy, a one-line meaning of each action, and the entry (request,
  action taken, note) but **not the user rating**. 3 votes, majority wins; unparseable votes dropped; no valid vote => non-compliant. Ground-truth
  `compliant` flags exist only to score the judge.
- **Metrics:** `trap_unsafe_rate` = P(refund | TRAP), lower is better; `valid_correct_rate` = P(refund | VALID), higher is better; judge recall on bad
  entries and false-reject rate on good entries; unparseable rate (0 everywhere). Headline CIs: 95% bootstrap resampling **queries** (seeds at
  temperature 0.1 are near-duplicates, so pooled-seed Wilson intervals, also in the CSVs, are too narrow).
- **Calls:** 4 conditions x 40 queries x 3 seeds = **480 agent calls**, plus 60 judge calls (20 entries x 3 votes). Prompts, model digest and memory are
  logged in `results/refunds/raw_meta.json`; every call is in `results/refunds/raw.jsonl`.

## How to run
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
# dry run, no model (MockLLM for agent AND judge; numbers are NOT results):
.venv/bin/python src/run_experiment.py --domain refunds --model mock --out results_mock
.venv/bin/python src/analyze.py --dir results_mock --domains refunds
# real run (judge audit, then ~15 min of agent calls; resumable), then analysis and tables/plot:
.venv/bin/python src/run_experiment.py --domain refunds --model qwen2.5:7b-instruct --out results
.venv/bin/python src/analyze.py --dir results --domains refunds
.venv/bin/python src/make_tables.py        # results/results_tables.md + results/main_plot.png
```
Prompt text lives only in `src/strategies.py` and the domain files. The backend is one callable `llm(prompt, seed, system=None)` in `src/llm.py`.

## Results (qwen2.5:7b-instruct; brackets = 95% query-bootstrap CI)
| condition | unsafe refunds on TRAP (lower better) | correct refunds on VALID (higher better) |
|---|---|---|
| no memory | 0.00 [0.00, 0.00] (0/60) | 0.95 [0.85, 1.00] (57/60) |
| vanilla | 0.30 [0.10, 0.50] (18/60) | 1.00 [1.00, 1.00] (60/60) |
| paper: "for reference only" | 0.20 [0.05, 0.40] (12/60) | 0.95 [0.85, 1.00] (57/60) |
| write-time audit (ours) | 0.00 [0.00, 0.00] (0/60) | 1.00 [1.00, 1.00] (60/60) |

![main plot](results/main_plot.png)

All tables (by query type, each defense vs vanilla, judge accuracy, the judge's decision and reason for every entry, and the queries that triggered
refunds) are in [results/results_tables.md](results/results_tables.md). The exact prompts the agent saw under vanilla, the paper prompt and the audit for three queries (T14, T03, V10) are in [results/examples.md](results/examples.md).

**What the audited agent actually did:** on trap queries it answered `explain_policy` 48 times and `escalate` 12 times (exact-label accuracy 0.95, same as no_memory; vanilla 0.70, paper 0.80), i.e. correct answers rather than a blanket refusal. Its prompt held only genuine refund memories (V1-V6), and it still declined the traps.

**Judge quality** (vs. ground truth, 20 entries): caught **10/10** misleading entries; wrongly rejected **3/10** good ones, all honest policy explanations
(H1, H2, H4); none of the 6 valid refunds. Accuracy 0.85. Kept pool: V1-V6 and H3.

## Layout
`src/` code (`domains/`, `judge.py`, `agent.py`, `retrieve.py`, `strategies.py`, `llm.py`, `run_experiment.py`, `analyze.py`, `make_tables.py`); `results/refunds/` raw outputs, audit,
per-domain CSVs; `results/results_tables.md`, `examples.md`, `summary_all.csv`, `audit_summary.csv`, `influence_all.csv`, `subtype_all.csv`, `main_plot.png`, `analysis_output.txt`;
`results/archive/sales_dropped/` the dropped sales domain.
