"""Hourly quiz pipeline: fetch questions, answer any round not yet answered,
commit answers/round-NNNN.json files, push to main.

Run by launchd every few minutes; safe to run repeatedly (idempotent).
"""
import csv
import io
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

from solver import solve

REPO = os.path.dirname(os.path.abspath(__file__))
SRC = "repos/FaisalXL/dso429-hourly-quiz/contents/questions.csv"


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def run(*cmd, **kw):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, **kw)


def fetch_questions():
    # The contents API is fresher than raw.githubusercontent.com (which caches).
    r = run("gh", "api", "-H", "Accept: application/vnd.github.raw", SRC)
    if r.returncode != 0 or not r.stdout.startswith("round_id"):
        raise RuntimeError("fetch failed: " + r.stderr[:300])
    return list(csv.DictReader(io.StringIO(r.stdout)))


def llm_fallback(row):
    prompt = (
        "Answer this multiple choice business-arithmetic question. Reply with "
        "only the single letter A, B, C or D.\n\n"
        f"{row['question_text']}\nA) {row['option_a']}\nB) {row['option_b']}\n"
        f"C) {row['option_c']}\nD) {row['option_d']}"
    )
    r = subprocess.run(["claude", "-p", "--model", "sonnet", prompt],
                       capture_output=True, text=True, timeout=120)
    for ch in r.stdout.strip().upper():
        if ch in "ABCD":
            return ch
    return "A"


def main():
    r = run("git", "pull", "--rebase", "--autostash", "origin", "main")
    if r.returncode != 0:
        log("pull failed:", r.stderr[:300])
    rows = fetch_questions()
    rounds = defaultdict(list)
    for row in rows:
        rounds[int(row["round_id"])].append(row)

    os.makedirs(os.path.join(REPO, "answers"), exist_ok=True)
    written = []
    for rid in sorted(rounds, reverse=True):  # newest first
        path = os.path.join(REPO, "answers", f"round-{rid:04d}.json")
        qs = rounds[rid]
        if os.path.exists(path) or len({q["q_index"] for q in qs}) < 25:
            continue
        answers = {}
        for q in sorted(qs, key=lambda q: int(q["q_index"])):
            a, how = solve(q)
            if a is None:
                log(f"round {rid} q{q['q_index']} unmatched; using LLM fallback")
                a = llm_fallback(q)
            answers[f"q{q['q_index']}"] = a
        with open(path, "w") as f:
            json.dump({"round_id": rid, "answers": answers}, f, indent=1)
        written.append(rid)

    if not written:
        log("nothing new")
        return
    run("git", "add", "answers")
    msg = f"Answers for rounds {min(written)}-{max(written)}" if len(written) > 1 else f"Answers for round {written[0]}"
    c = run("git", "commit", "-m", msg)
    if c.returncode != 0:
        log("commit failed:", c.stdout[:300], c.stderr[:300])
        sys.exit(1)
    p = run("git", "push", "origin", "main")
    if p.returncode != 0:
        log("push failed:", p.stderr[:300])
        sys.exit(1)
    log(f"pushed {len(written)} rounds: {sorted(written)[0]}..{sorted(written)[-1]}")


if __name__ == "__main__":
    main()
