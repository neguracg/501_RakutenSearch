import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
old = json.load(open(sys.argv[1], encoding="utf-8"))
new = json.load(open(sys.argv[2], encoding="utf-8"))
def grade(truth, r):
    conf = r[0]
    if conf == "EXC":
        return "EXC"
    if conf != "high":
        return "UNK"           # low / none : safe but no unit price
    kind = truth[0]
    cnt, meas, dim = r[1], r[5], r[4]
    if kind == "LOW":
        return "RISK"          # ambiguous string but returned high
    if kind == "AMB":
        return "OK" if cnt in truth[1] else "WRONG"
    if kind == "c":
        return "OK" if cnt == truth[1] else "WRONG"
    if kind == "cm":
        if cnt != truth[1]:
            return "WRONG"
        if dim != truth[2] or meas is None or abs(meas - truth[3]) > 1e-6 * max(1, truth[3]):
            return "WRONG"
        return "OK"
def fmt(r):
    return f"{r[0]} c={r[1]} {r[2]} amt={r[3]} {r[4]} m={r[5]}"
from collections import Counter
co, cn = Counter(), Counter()
rows = []
for (t, tr, ro), (t2, tr2, rn) in zip(old, new):
    assert t == t2
    go, gn = grade(tr, ro), grade(tr, rn)
    co[go] += 1; cn[gn] += 1
    rows.append((t, tr, ro, rn, go, gn))
print("OLD(466cacc):", dict(co))
print("NEW(71dc9aa):", dict(cn))
print()
print("=== REGRESSIONS: OK/UNK -> WRONG (new wrong-high) ===")
for t, tr, ro, rn, go, gn in rows:
    if gn == "WRONG" and go != "WRONG":
        print(f"[{go}->{gn}] {t}\n    truth={tr}\n    old: {fmt(ro)}\n    new: {fmt(rn)}")
print()
print("=== STILL WRONG in both (pre-existing) ===")
for t, tr, ro, rn, go, gn in rows:
    if gn == "WRONG" and go == "WRONG":
        print(f"[{go}->{gn}] {t}\n    truth={tr}\n    old: {fmt(ro)}\n    new: {fmt(rn)}")
print()
print("=== AVAILABILITY LOSS: OK -> UNK ===")
for t, tr, ro, rn, go, gn in rows:
    if go == "OK" and gn == "UNK":
        print(f"[{go}->{gn}] {t}   truth={tr}\n    new: {fmt(rn)}")
print()
print("=== NEW WRONG->FIXED (old WRONG, new OK/UNK) ===")
for t, tr, ro, rn, go, gn in rows:
    if go == "WRONG" and gn != "WRONG":
        print(f"[{go}->{gn}] {t}   truth={tr}\n    old: {fmt(ro)}\n    new: {fmt(rn)}")
print()
print("=== RISK (ambiguous but high) ===")
for t, tr, ro, rn, go, gn in rows:
    if gn == "RISK":
        print(f"[{go}->{gn}] {t}\n    old: {fmt(ro)}\n    new: {fmt(rn)}")
print()
print("=== UNK->OK (gains) ===")
n=0
for t, tr, ro, rn, go, gn in rows:
    if go == "UNK" and gn == "OK":
        n+=1
print(n, "gains")
