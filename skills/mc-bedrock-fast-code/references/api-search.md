# API And Official-Name Search

Use existing indexes immediately. Do not run project detection, version discovery, downloads, or index updates before a normal lookup.

## API Interfaces And Events

Query interfaces or events by the type stated by the user:

```bash
python scripts/query_knowledge.py --registry ~/.codex/mc-bedrock-fast-code-data/knowledge_registry.json CanSee --source api --api-kind interface
python scripts/query_knowledge.py --registry ~/.codex/mc-bedrock-fast-code-data/knowledge_registry.json PlayerFishingAfterServerEvent --source api --api-kind event
```

The first pass respects the stated type. On zero results, the query checks the other API type, then development-guide/tutorial indexes and downloaded pages. Use `--api-only` to forbid non-API fallback. Use `--include-non-api-docs` when broader docs should be searched even after an API hit.

API indexes preserve official return-value and remark sections. Read those fields before concluding that no solution exists; remarks often describe failure semantics, side effects, capacity limits, or indirect ways to answer a behavioral question.

When the user gives a natural-language behavior instead of an API name:

1. Extract one or more distinctive English identifiers or domain terms.
2. Search the type the user stated first.
3. Inspect return values and notes for indirect solutions.
4. If the stated type misses, allow the automatic type fallback.
5. Report whether the answer is direct, inferred from documented behavior, or absent.

## Demo, Vanilla, And Custom Sources

Use source selection deliberately:

```bash
python scripts/query_knowledge.py --registry <registry> UIDemo --kind ui --source demo
python scripts/query_knowledge.py --registry <registry> zombie --kind render_controller --source vanilla
python scripts/query_knowledge.py --registry <registry> entity_alphatest --kind material --source vanilla
python scripts/query_knowledge.py --registry <registry> <term> --source custom
```

For Microsoft Bedrock JSON schemas, components, format versions, Molang names, and bedrock.dev stable/beta references, query the separate JSON-document tree:

```bash
python scripts/query_knowledge.py --registry <registry> minecraft:health --source minecraft-json
python scripts/query_knowledge.py --registry <registry> format_version --source microsoft
python scripts/query_knowledge.py --registry <registry> minecraft:client_entity --source bedrock-dev
```

Prefer Microsoft Creator documentation as the official authority. Treat bedrock.dev as a useful community-organized stable/beta reference and identify its source in answers. Do not crawl either site during an ordinary query; report a missing `minecraft_json_docs` registry entry when this source is required.

Queries use `search.sqlite3` in this order: exact identifier, exact format version, weighted FTS, then trigram FTS. Results prioritize Microsoft stable documentation and stable bedrock.dev pages before preview/beta pages. If SQLite is missing, incompatible, corrupt, or has no result, `pages.jsonl` remains the compatibility and substring-search fallback.

For project-local display names or IDs, search `texts/zh_CN.lang` first. Custom-index queries already prioritize that file.

## Result Rules

- Distinguish interfaces from events and identify client/server side.
- Prefer exact identifier hits, then behavior/remark matches, then broader documentation.
- Use custom indexes for local conventions, NetEase official indexes for ModAPI validity, Microsoft Creator docs for Bedrock JSON authority, bedrock.dev for community-organized stable/beta references, demos for fixed routines, and vanilla indexes for built-in resource names.
- Do not claim an API exists when all relevant prepared sources miss.
- If a required index is missing, name only that source and use the separate [knowledge setup skill](../../mc-bedrock-knowledge-setup/SKILL.md) when preparation is necessary. Ordinary zero-result queries do not trigger rebuilding.
