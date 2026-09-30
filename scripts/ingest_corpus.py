from pathlib import Path
import os
import requests
import frontmatter

corpus_path = Path(__file__).resolve().parent.parent / "corpus"
ingest_url = os.environ.get("INGEST_URL", "http://127.0.0.1:8000") + "/documents/ingest"
failures = []
skipped_files = []
ingested_files = []


for path in corpus_path.rglob("*.md"):
    if path.name.lower() == "_index.md":
        continue  # Skip index.md files
    try:
        post = frontmatter.load(path)
        content = post.content
        relative_title = path.relative_to(corpus_path).as_posix()
        print(f"Processing {relative_title}...")
        if len(content) < 250:
            print(f"Skipping {relative_title} due to insufficient content length.")
            skipped_files.append(relative_title)
            continue
        response = requests.post(
            ingest_url,
            json={"title": relative_title,"content": content},
            timeout = 120
            )
        response.raise_for_status()
        ingested_files.append(relative_title)
        print(f"Successfully ingested {relative_title}.")

    except Exception as e:
        print(f"Error processing {path}: {e}")
        failures.append((path, str(e)))


if failures:
    for path, error in failures:
        print(f"  {path}: {error}")
else:
    print("All files processed successfully without errors.")
    
    
print("Ingestion completed.")
print(f"Total files processed: {len(ingested_files) + len(skipped_files) + len(failures)}")
print(f"Successfully ingested: {len(ingested_files)}")
print(f"Skipped files: {len(skipped_files)}")
print(f"Failed files: {len(failures)}")
print("Ingested files:")
for file in ingested_files:
    print(f"  {file}")