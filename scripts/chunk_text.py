#!/usr/bin/env python3
import sys

if len(sys.argv) < 4:
    print("usage: chunk_text.py <input> <output_prefix> <max_chars>")
    sys.exit(1)

input_path = sys.argv[1]
output_prefix = sys.argv[2]
max_chars = int(sys.argv[3])

with open(input_path, "r", encoding="utf-8") as f:
    text = f.read()

chunks = []
current = []
count = 0
for ch in text:
    current.append(ch)
    count += 1
    if count >= max_chars:
        chunks.append("".join(current))
        current = []
        count = 0
if current:
    chunks.append("".join(current))

for i, chunk in enumerate(chunks):
    out_path = f"{output_prefix}{i:02d}"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(chunk)
