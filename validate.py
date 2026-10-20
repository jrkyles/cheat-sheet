"""Check solver.py against the practice answer keys (rounds 1-48)."""
import csv
from solver import solve

rows = list(csv.DictReader(open("data/questions.csv")))
key = {(r["round_id"], r["q_index"]): r["answer"] for r in csv.DictReader(open("data/practice_keys.csv"))}
ok = bad = unm = 0
for r in rows:
    k = (r["round_id"], r["q_index"])
    if k not in key:
        continue
    a, how = solve(r)
    if a is None:
        unm += 1
        print("UNMATCHED", r["question_text"], [r["option_" + c] for c in "abcd"])
    elif a == key[k]:
        ok += 1
    else:
        bad += 1
        print("WRONG", a, key[k], r["question_text"], [r["option_" + c] for c in "abcd"])
print(f"correct={ok} wrong={bad} unmatched={unm}")

# Graded rounds: how many are not solvable by templates?
gu = sum(1 for r in rows if (r["round_id"], r["q_index"]) not in key and solve(r)[0] is None)
print("graded-round questions unmatched:", gu)
