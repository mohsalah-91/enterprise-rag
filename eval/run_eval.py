import json
import os
import requests
from pathlib import Path

GOLDEN_SET = Path(__file__).resolve().parent / "golden_set.jsonl"
eval_url = os.environ.get("EVAL_URL", "http://127.0.0.1:8000") + "/documents/search"

with open(GOLDEN_SET, "r", encoding="utf-8") as f:
     # Check if the line is not empty
    golden_set = [json.loads(line) for line in f if line.strip()]
    print(f"Loaded {len(golden_set)} entries from golden_set.jsonl")

for entry in golden_set:
    entry_id = entry.get("id")
    question = entry.get("question")
    entry_type = entry.get("type")
    print(f"ID: {entry_id}, Question: {question}, Type: {entry_type}")


for i, entry in enumerate(golden_set):
    entry_id = entry.get("id")
    question = entry.get("question")
    entry_type = entry.get("type")
    print(f"Sending question to evaluation endpoint: {question}")
    response = requests.post(
        eval_url,
        json={"query": question, "limit": 5},
        timeout = 60
    )
    for rank, chunk in enumerate(response.json(), start=1):
        print(f"  {rank}. [{chunk['rerank_score']:.3f}] {chunk['title']} (chunk {chunk['chunk_index']})")
        print(f"     {chunk['content'][:120]}...")
    if i >= 2:
        break # Limit to the first two questions for testing purposes


def find_hit_rank(chunks, must_contain):
    for rank, chunk in enumerate(chunks, start=1):
        if must_contain in chunk['content']:
            return rank
    return None