import sys
from pathlib import Path

inp = Path(sys.argv[1])
limit = int(sys.argv[2])
out_prefix = sys.argv[3]
text = inp.read_text()
chunks = [text[i:i + limit] for i in range(0, len(text), limit)]
for i, c in enumerate(chunks, 1):
    Path(f"{out_prefix}{i}.txt").write_text(c)
print(len(chunks))
