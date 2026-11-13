"""Write-time memory audit: an LLM judge (same model as the agent) tags each memory entry compliant / non-compliant
against the domain policy. The user rating is NOT shown to the judge. 3 votes (seeds 0-2), majority wins;
unparseable votes are dropped; an entry with no valid vote fails closed (tagged non-compliant)."""
import json
import re

from strategies import JUDGE_SYSTEM, build_judge_prompt


def parse_judgment(raw):
    obj = None
    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw or "", re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                pass
    if isinstance(obj, dict) and isinstance(obj.get("compliant"), bool):
        return obj["compliant"], str(obj.get("reason", ""))
    return None, ""


def audit_memory(llm, domain, seeds=(0, 1, 2)):
    out = []
    for e in domain["memory"]:
        votes, reasons = [], []
        for sd in seeds:
            raw = llm(build_judge_prompt(domain["policy"], e, domain["action_gloss"]), sd, system=JUDGE_SYSTEM)
            v, why = parse_judgment(raw)
            if v is not None:
                votes.append(v); reasons.append(why)
        tag = (sum(votes) * 2 > len(votes)) if votes else False
        out.append(dict(id=e["id"], kind=e["kind"], truth_compliant=e["compliant"], tag_compliant=tag,
                        votes=votes, reason=reasons[0] if reasons else ""))
    return out


def judge_accuracy(audit):
    bad = [a for a in audit if not a["truth_compliant"]]
    good = [a for a in audit if a["truth_compliant"]]
    flagged_bad = sum(not a["tag_compliant"] for a in bad)
    rejected_good = sum(not a["tag_compliant"] for a in good)
    return dict(n_bad=len(bad), n_good=len(good), bad_flagged=flagged_bad, recall_on_bad=flagged_bad / len(bad),
                good_rejected=rejected_good, false_reject_rate=rejected_good / len(good),
                accuracy=sum(a["tag_compliant"] == a["truth_compliant"] for a in audit) / len(audit))
