# Microsoft Bedrock JSON Knowledge Setup

Load this workflow only for first installation, an explicit Microsoft Learn/bedrock.dev update, index repair, or a missing `minecraft_json_docs` index that blocks the task. Do not load or run it during ordinary project editing and lookup.

## Build

Store generated knowledge outside the skill, normally under `~/.codex/mc-bedrock-fast-code-data`:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --minecraft-json-docs
```

The crawler discovers Microsoft Creator pages through its `toc.json` and bedrock.dev stable/beta pages through its sitemap. It obeys `robots.txt`, downloads concurrently, retries transient failures, prints continuous progress, and reuses cached pages. A first full run contains many pages; allow it enough time to finish and do not terminate it merely for running a long time.

Select one source for targeted maintenance:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --minecraft-json-docs --minecraft-json-source microsoft
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --minecraft-json-docs --minecraft-json-source bedrock-dev
```

Use `--minecraft-json-workers <count>` to tune concurrency. Use `--minecraft-json-max-pages <count>` only for smoke tests because it intentionally creates an incomplete selected tree.

## Rebuild Search Indexes

Rebuild `index.json` and `search.sqlite3` from the existing `pages.jsonl` without accessing either website:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --minecraft-json-docs --minecraft-json-reindex
```

SQLite uses exact B-tree indexes for identifiers and format versions, weighted FTS5 for full text, optional trigram FTS5 for substring/Chinese lookup, and FTS4 as a compatibility fallback. Queries retain `pages.jsonl` as the final fallback.

## Verify

Verify `<root>/knowledge_registry.json` contains `minecraft_json_docs`. Under that directory, verify `pages.jsonl`, `index.json`, and `search.sqlite3` exist and the SQLite `PRAGMA integrity_check` result is `ok`. Keep raw HTML and generated indexes outside the distributed skill package.
