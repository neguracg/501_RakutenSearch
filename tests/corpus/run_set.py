import sys, io, json, os
src, outp = sys.argv[1], sys.argv[2]
sys.path.insert(0, src)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shopping.quantity import parse_quantity
import patterns
out = []
for title, truth in patterns.P:
    try:
        q = parse_quantity(title)
        r = [q.confidence, q.count_total, q.count_unit, q.content_amount, q.content_dimension, q.measure_total]
    except Exception as e:
        r = ["EXC", repr(e), None, None, None, None]
    out.append([title, list(truth), r])
with open(outp, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print(len(out), "patterns ->", outp)
