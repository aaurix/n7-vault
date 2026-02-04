import textwrap
from pathlib import Path

src = Path('/Users/massis/clawd/state/summary_whatsapp.txt')
text = src.read_text()
max_len = 1400
chunks = []
cur = ''
for para in text.split('\n'):
    if cur:
        candidate = cur + '\n' + para
    else:
        candidate = para
    if len(candidate) <= max_len:
        cur = candidate
    else:
        if cur:
            chunks.append(cur)
        if len(para) <= max_len:
            cur = para
        else:
            for part in textwrap.wrap(para, max_len, break_long_words=False, break_on_hyphens=False):
                chunks.append(part)
            cur = ''
if cur:
    chunks.append(cur)

out_dir = Path('/Users/massis/clawd/state/summary_chunks')
out_dir.mkdir(parents=True, exist_ok=True)
for i, chunk in enumerate(chunks, 1):
    (out_dir / f'chunk_{i}.txt').write_text(chunk)
print(len(text))
print(len(chunks))
