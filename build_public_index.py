#!/usr/bin/env python3
"""Build a lightweight public index package from local generated indexes.

This intentionally keeps only metadata needed for lookup. It does not copy
official game/demo source JSON, textures, models, sounds, or scripts.
"""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
OUT = ROOT / "public-index"
ZIP = ROOT / "mc-bedrock-fast-code-public-index.zip"

KEEP_KINDS = {
    "behavior_entity",
    "client_entity",
    "behavior_item",
    "client_item",
    "render_controller",
    "animation_controller",
    "animation",
    "geometry",
    "texture",
    "texture_atlas",
    "particle",
    "sound_definition",
    "ui",
    "attachable",
    "recipe",
    "loot_table",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compact_record(rec: dict) -> dict:
    refs = rec.get("references") or {}
    compact_refs = {}
    if isinstance(refs, dict):
        for key, value in refs.items():
            if isinstance(value, list):
                compact_refs[key] = [str(v) for v in value[:12]]
            elif isinstance(value, dict):
                compact_refs[key] = {str(k): str(v)[:160] for k, v in list(value.items())[:12]}
            elif value:
                compact_refs[key] = str(value)[:160]
    return {
        "kind": rec.get("kind"),
        "pack_type": rec.get("pack_type"),
        "pack_name": rec.get("pack_name"),
        "relative_path": rec.get("relative_path"),
        "identifier": rec.get("identifier"),
        "name": rec.get("name"),
        "components": [str(v) for v in (rec.get("components") or [])[:40]],
        "references": compact_refs,
        "tags": [str(v) for v in (rec.get("tags") or [])[:20]],
    }


def build_vanilla(version: str) -> dict:
    src = WORKSPACE / "mc_bedrock_local_indexes" / version / "index.json"
    data = load(src)
    records = [
        compact_record(rec)
        for rec in data.get("records", [])
        if rec.get("kind") in KEEP_KINDS
    ]
    return {
        "source": "locally generated summary from MinecraftPE_Netease data files",
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "original_stats": data.get("stats"),
        "included_kinds": sorted(KEEP_KINDS),
        "record_count": len(records),
        "kind_counts": dict(sorted(Counter(r["kind"] for r in records).items())),
        "records": records,
    }


def build_demo() -> dict:
    src = WORKSPACE / "mc_bedrock_demo_index" / "demo_index.json"
    data = load(src)
    records = []
    for rec in data.get("records", []):
        meta = rec.get("json") if isinstance(rec.get("json"), dict) else {}
        records.append({
            "source": "NetEase public demo metadata summary",
            "demo": rec.get("demo"),
            "path": rec.get("path"),
            "category": rec.get("category"),
            "suffix": rec.get("suffix"),
            "size": rec.get("size"),
            "identifier": meta.get("identifier") if isinstance(meta, dict) else None,
            "minecraft_type": meta.get("minecraft_type") if isinstance(meta, dict) else None,
            "format_version": meta.get("format_version") if isinstance(meta, dict) else None,
        })
    return {
        "source": "metadata summary from NetEase public demo packs; no original assets/scripts copied",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "category_counts": dict(sorted(Counter(r["category"] for r in records).items())),
        "records": records,
    }


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if OUT.exists():
        for path in sorted(OUT.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    OUT.mkdir(parents=True, exist_ok=True)
    versions = ["3.7.0.292435", "3.8.0.292301"]
    manifest = {
        "name": "mc-be-hub-skills public lightweight index",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "license_note": "Metadata-only summary. Official Minecraft/NetEase assets and source files are not included.",
        "versions": versions,
        "files": [],
    }
    for version in versions:
        rel = Path("vanilla") / f"{version}.summary.json"
        write_json(OUT / rel, build_vanilla(version))
        manifest["files"].append(rel.as_posix())
    write_json(OUT / "demos.summary.json", build_demo())
    manifest["files"].append("demos.summary.json")
    write_json(OUT / "manifest.json", manifest)
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(OUT))
    print(f"Wrote {ZIP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
