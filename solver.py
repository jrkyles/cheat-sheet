"""Deterministic solvers for the Hourly Quiz question templates.

solve(row) returns (letter, how) where how is "template" or "unmatched".
Unmatched questions are left to the caller (pipeline falls back to an LLM).
"""
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
NUM = r"-?\$?[\d,]*\.?\d+"


def n(s):
    return float(s.replace("$", "").replace(",", "").rstrip("."))


def ratio_split(m):
    total, a, b = n(m[1]), n(m[2]), n(m[3])
    return total * a / (a + b)


# (regex, function(match) -> number | date)
NUMERIC = [
    (r"An investment of (\$[\d,.]+) grows at ([\d.]+)% compounded annually\. What is its value after (\d+) years",
     lambda m: n(m[1]) * (1 + n(m[2]) / 100) ** int(m[3])),
    (r"generates (\$[\d,.]+) in revenue against (\$[\d,.]+) in cost of goods sold\. What is the gross margin",
     lambda m: (n(m[1]) - n(m[2])) / n(m[1]) * 100),
    (r"headcount series runs ([\d, ]+)\. If the pattern continues",
     lambda m: _next_term([int(x) for x in m[1].split(",")])),
    (r"listed at (\$[\d,.]+) is discounted by ([\d.]+)%",
     lambda m: n(m[1]) * (1 - n(m[2]) / 100)),
    (r"moved from (\$[\d,.]+) to (\$[\d,.]+)\. What is the percentage change",
     lambda m: (n(m[2]) - n(m[1])) / n(m[1]) * 100),
    (r"Fixed costs are (\$[\d,.]+)\. Each unit sells for (\$[\d,.]+) with a variable cost of (\$[\d,.]+)",
     lambda m: n(m[1]) / (n(m[2]) - n(m[3]))),
    (r"A (\$[\d,.]+) marketing budget is split between two channels in the ratio (\d+):(\d+)\. What does the first channel receive",
     ratio_split),
    (r"Region A had ([\d,]+) orders averaging (\$[\d,.]+); region B had ([\d,]+) orders averaging (\$[\d,.]+)",
     lambda m: (n(m[1]) * n(m[2]) + n(m[3]) * n(m[4])) / (n(m[1]) + n(m[3]))),
    (r"invoice for (\$[\d,.]+) is converted to euros at ([\d.]+) euros per US dollar",
     lambda m: n(m[1]) * n(m[2])),
    (r"holds (\d+) billing tickets, (\d+) technical tickets and (\d+) account tickets\. .* billing ticket",
     lambda m: n(m[1]) / (n(m[1]) + n(m[2]) + n(m[3])) * 100),
    (r"sells ([\d,]+) units at (\$[\d,.]+) each\. What is total revenue",
     lambda m: n(m[1]) * n(m[2])),
]
DATE_RE = r"signed on (\d+) (\w+) (\d{4}) has a (\d+)-day settlement period"


def _next_term(seq):
    d = seq[1] - seq[0]
    if all(b - a == d for a, b in zip(seq, seq[1:])):
        return seq[-1] + d
    r = seq[1] / seq[0]
    if all(abs(b / a - r) < 1e-9 for a, b in zip(seq, seq[1:])):
        return seq[-1] * r
    raise ValueError("unknown sequence")


def opt_value(text):
    t = text.replace("units", "").replace("$", "").replace(",", "").replace("%", "").strip()
    return float(t)


def solve(row):
    q = row["question_text"]
    opts = {c.upper(): row["option_" + c] for c in "abcd"}

    m = re.search(DATE_RE, q)
    if m:
        d = date(int(m[3]), MONTHS.index(m[2]) + 1, int(m[1])) + timedelta(days=int(m[4]))
        want = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
        hits = [k for k, v in opts.items() if v.strip() == want]
        return (hits[0], "template") if len(hits) == 1 else (None, "unmatched")

    for pat, fn in NUMERIC:
        m = re.search(pat, q)
        if not m:
            continue
        try:
            val = fn(m)
        except Exception:
            return None, "unmatched"
        # Match on the displayed precision of each option, so rounding in the
        # option text (e.g. 10.4%, 667 units) agrees with the exact value.
        hits = []
        for k, v in opts.items():
            try:
                ov = opt_value(v)
            except ValueError:
                continue
            dec = len(v.split(".")[1].rstrip("% units")) if "." in v else 0
            q_ = Decimal(1).scaleb(-dec)
            if Decimal(repr(val)).quantize(q_, ROUND_HALF_UP) == Decimal(repr(ov)).quantize(q_, ROUND_HALF_UP):
                hits.append(k)
        if len(hits) == 1:
            return hits[0], "template"
        # Fallback: closest option, accepted only if clearly closest.
        try:
            ranked = sorted(opts, key=lambda k: abs(opt_value(opts[k]) - val))
            d0 = abs(opt_value(opts[ranked[0]]) - val)
            d1 = abs(opt_value(opts[ranked[1]]) - val)
            if d0 * 20 < d1 and d0 <= max(0.01 * abs(val), 0.51):
                return ranked[0], "template"
        except ValueError:
            pass
        return None, "unmatched"
    return None, "unmatched"
