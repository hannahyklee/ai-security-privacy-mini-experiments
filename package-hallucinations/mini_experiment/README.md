# Mini experiment: can a small local LLM detect hallucinated Python packages?

A toy follow-up to the self-detection mitigation in *We Have a Package for You!* (see [README.md](README.md) for the original paper repo). We ask a local model, "Is X a valid Python package?", for three kinds of names and measure how often it accepts each.

All code, data and outputs are in [mini_experiment/](mini_experiment/). The paper's own code is unchanged; we reuse its detection prompt (from `Mitigation/Hallucination_Detection_Query.py`) and its data in `Data/Python/`.

## Setup

- **Model:** `qwen2.5-coder:7b` via Ollama (temperature 0.7, 5 samples per package).
- **Prompt:** the paper's system message (answer only Yes or No) plus "Is {package} a valid Python package?".
- **Datasets (100 packages each, listed in `datasets.json`):**
  - *Popular:* the top 100 PyPI packages by 30-day downloads ([hugovk/top-pypi-packages](https://hugovk.github.io/top-pypi-packages/)).
  - *Rare:* real packages sampled from ranks ~10,000-15,000 of that list, each confirmed on PyPI.
  - *Hallucinated:* names the same model recommended for the paper's LLM-generated prompts, kept only if absent from both the PyPI snapshot in `Data/Python/` and live PyPI (404). Stdlib modules, placeholders and mangled submodule paths are filtered out.
- A package is **accepted** if at least 3 of its 5 answers are "Yes".

## Reproduce

Requires [Ollama](https://ollama.com) running with `qwen2.5-coder:7b` pulled, [uv](https://docs.astral.sh/uv/), and Python 3.10+.

```bash
cd mini_experiment
python3.12 build_datasets.py 100   # downloads nothing new if top-pypi-packages.json is present; queries PyPI and Ollama
python3.12 run_detection.py        # 100 x 3 x 5 = 1,500 model calls -> results.csv
python3.12 evaluate.py             # -> summary.md
uv run python analyze.py           # tables and figures -> out/
```

Phantom generation is not deterministic, so re-running `build_datasets.py` produces a different hallucinated list. `datasets.json` records the one used for the reported results.

## Files

| file | purpose |
|---|---|
| `build_datasets.py` | builds `datasets.json` |
| `run_detection.py` | queries Ollama, writes `results.csv` |
| `evaluate.py` | quick metrics, writes `summary.md` |
| `analyze.py` | tables (`out/table*.txt`) and figures (`out/fig*.png`) |
| `common.py` | Ollama chat and PyPI existence helpers |
| `top-pypi-packages.json` | download-ranked package list snapshot |
