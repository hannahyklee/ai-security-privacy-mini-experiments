# Results

Model answers 'Is X a valid Python package?'. Per-sample accuracy: Yes for real, No for hallucinated.

| dataset | packages | per-sample acc | majority-vote acc | mean consistency | invalid rate | 'Yes' rate |
|---|---|---|---|---|---|---|
| popular | 10 | 96% | 100% | 96% | 0% | 96% |
| rare | 10 | 70% | 70% | 88% | 0% | 70% |
| hallucinated | 10 | 32% | 30% | 94% | 0% | 68% |

Overall (hallucinated = positive): precision 0.48, recall 0.32, F1 0.39, false-positive rate 0.17 (TP=16 FP=17 FN=34 TN=83, invalid answers excluded).

## Packages misclassified by majority vote
- **rare** `guppylang-internals`: {'no': 5}
- **rare** `runai-model-streamer-azure`: {'yes': 2, 'no': 3}
- **rare** `dagster-sling`: {'no': 4, 'yes': 1}
- **hallucinated** `azure-mgmt-namespace`: {'yes': 5}
- **hallucinated** `cockroachdb-python`: {'yes': 5}
- **hallucinated** `vertica-hive`: {'yes': 3, 'no': 2}
- **hallucinated** `pytest-snapshots`: {'yes': 5}
- **hallucinated** `pytest-json-reporter`: {'yes': 5}
- **hallucinated** `django-xstatic-jquery`: {'yes': 5}
- **hallucinated** `authorization`: {'yes': 5}
