# Knowledge Installation And Maintenance

Load this workflow only for first installation, explicit updates, repairs, or missing-index recovery. Do not run it during normal project editing or ordinary API lookup.

## Default Storage

Store reusable data under `~/.codex/mc-bedrock-fast-code-data` unless the user chooses another external root. The registry is `<root>/knowledge_registry.json`.

## Official Documentation

Build all official documentation trees and the API index:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --api-docs
```

The updater crawls `mcdocs`, `mcguide`, and `mconline`, writes separate indexes, downloads concurrently, and prints progress. Allow it enough time to finish. Use targeted maintenance only when one non-API tree is known to have changed:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --development-guides
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --tutorial-docs
```

## Installed Vanilla Data

Ask for the MCStudio/MinecraftPE_Netease install root or exact version folder before searching broadly. Ask which representative major versions to index; prefer one version per major release unless comparison is requested.

List versions without building:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --mc-root <.../MCStudioDownload/game/MinecraftPE_Netease> --list-versions-only
```

Build vanilla indexes:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --vanilla-index --mc-root <.../MinecraftPE_Netease> --pretty
```

Use `--version-dir <version-folder>` for an exact version. Use `--auto-search` only after warning that discovery may be slow.

## Official Demo Projects

Index one or more official demo roots:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --demo-source ./6-1DemoMod --demo-source "<path-to-6-4-resource-demo>" --pretty
```

Download the official public demo package when needed:

```bash
python scripts/download_demo_mirror.py --out ./mc-bedrock-official-public-demos
```

## Authorized Custom Project

Only after the user authorizes a local project, build a private style/content index:

```bash
python scripts/index_custom_project.py --project <path> --repo <optional-url-or-path> --root ~/.codex/mc-bedrock-fast-code-data --pretty
```

Keep custom data local, separate from official indexes, and out of releases.

## Remote Fallback

If local vanilla/demo preparation is unavailable, offer the coarse public index package:

```bash
python scripts/prepare_knowledge.py --root ~/.codex/mc-bedrock-fast-code-data --remote-indexes --remote-url <public-index-zip-url>
```

Treat it as lookup guidance, not version-specific authority.

## Verification

After preparation, inspect `knowledge_registry.json` and verify the selected key exists: `api_references`, `demo_index`, `vanilla_indexes`, `remote_public_indexes`, or `custom_project_indexes`. Do not require unrelated keys.
