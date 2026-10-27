# Project Editing And Diagnosis

Use this workflow for everyday ModSDK project work. Do not prepare or update knowledge before inspecting the requested code.

## Inspect The Project

Run project detection when the current workspace context is unclear:

```bash
python scripts/detect_project.py --project <cwd>
```

This checks project structure only. Use `--check-knowledge`, `--registry`, or `--root` solely during explicit setup/maintenance; do not inspect knowledge status during ordinary editing.

Treat the workspace as a NetEase project when it contains `studio.json`, valid pack manifests, `*Scripts`, `netease_*`, ModSDK imports, or calls such as `RegisterSystem`, `ListenForEvent`, `GetEngineCompFactory`, `BroadcastToServer`, or `NotifyToClient`.

Discover packs by scanning no more than two directory levels for the fixed filenames `pack_manifest.json` and `manifest.json`. Do not infer pack folders from suffixes such as `*_beh` or `*_res`. Require `header.name` to exactly match the containing folder name. Require a valid `header.uuid` that is unique across different pack folders. Classify `modules[].type: data` as a behavior pack and `modules[].type: resources` as a resource pack. Accept any number of valid behavior and resource packs in one project and validate all of them; a project may contain only one pack type.

Read applicable `AGENTS.md` files and preserve unrelated user changes. Inspect existing naming, pack suffixes, configuration, and nearby patterns before editing.

## Edit Or Generate

Use `scripts/fast_code.py` for supported deterministic scaffolds:

```bash
python scripts/fast_code.py create-pack --namespace demo_mod --out ./DemoMod --with-client --with-server
python scripts/fast_code.py add-ui --project ./DemoMod --namespace demo_mod --screen main
python scripts/fast_code.py add-entity --project ./DemoMod --namespace demo_mod --id squirrel
python scripts/fast_code.py add-item --project ./DemoMod --namespace demo_mod --id copper_coin
python scripts/fast_code.py add-block --project ./DemoMod --namespace demo_mod --id bright_block
```

Require these values before generation:

- New pack: namespace and output path/project name.
- Entity/item/block/UI/resource: project path, namespace, and local ID.

Accept full identifiers by splitting `<namespace>:<local_id>`. Keep identifiers lowercase with letters, digits, and underscores.

For specialized code changes, edit the existing project directly and match its conventions. Query official APIs only when validation is needed; read [api-search.md](api-search.md) at that point.

For shader changes, use [validation and delivery checks](shader-validation.md). To reuse a verified implementation or diagnose a familiar issue, search the external records through the [private experience workflow](experience-index.md); load only the matching record and verify its assumptions against the current project.

## Diagnose And Validate

Run the focused linter after generated or related structural changes:

```bash
python scripts/lint_project.py --project <project>
```

It checks malformed JSON, missing packs/UI definitions, and unresolved client-entity render/material/texture/geometry/animation references.

Do not include `studio.json` in routine post-edit change checks or summaries. MCStudio updates it when the user runs or tests the mod, so value changes there are expected unless the task explicitly edits or diagnoses that file.

Use Python environment checks only during setup or explicit interpreter/runtime troubleshooting:

```bash
python scripts/modsdk_python_env.py --project <project>
```

Prefer Python 2.7.18 for project syntax checks when available:

```bash
python scripts/check_python_syntax.py --project <project> --python <python-2.7.18>
```

Do not install `mc-netease-sdk` unless the selected interpreter is Python 2. Do not treat compilation as proof of ModSDK runtime behavior.

## Knowledge Usage

- Prefer an authorized custom local project index for style and naming.
- Validate API calls against official indexes.
- Use the Microsoft Creator/bedrock.dev JSON documentation index for Bedrock schemas, components, format versions, and JSON examples; prefer Microsoft as authority.
- Use demo indexes for official fixed routines.
- Use vanilla indexes for built-in components, render controllers, materials, textures, models, animations, and entity definitions.
- If a registry/key is missing, continue without it when safe. Only when the requested result depends on that source, read [knowledge setup](../../mc-bedrock-knowledge-setup/SKILL.md) and prepare that selected source.
