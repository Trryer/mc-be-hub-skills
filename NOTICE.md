# Notice And Disclaimer

## Project Status

`mc-be-hub-skills` is an unofficial developer automation toolkit for NetEase Minecraft Bedrock / MCStudio ModSDK addon workflows.

It is not affiliated with, endorsed by, sponsored by, or approved by Mojang, Microsoft, NetEase, or MCStudio.

## Source Materials

This repository may refer to or summarize metadata from:

- Public NetEase Minecraft/MCStudio ModSDK demo packs and tutorials.
- NetEase's public ModSDK demo page and official 3.8 demo download:
  - `https://mc.163.com/dev/mcmanual/mc-dev/mcguide/20-%E7%8E%A9%E6%B3%95%E5%BC%80%E5%8F%91/13-%E6%A8%A1%E7%BB%84SDK%E7%BC%96%E7%A8%8B/60-Demo%E7%A4%BA%E4%BE%8B.html`
  - `https://g79.gdl.netease.com/3.8Demo.zip`
- Public ModSDK documentation, including community mirrors such as `EaseCation/netease-modsdk-wiki`.
- Minecraft Bedrock / NetEase `MinecraftPE_Netease` game data installed locally by the user.

The skill scripts can generate indexes from those sources on the user's machine. Generated indexes should be stored outside the skill package.

## Public Lightweight Index

`mc-bedrock-fast-code-public-index.zip` is intended as a rough fallback for users who cannot or do not want to generate local indexes.

It contains metadata summaries only, such as:

- record kind
- identifier/name
- relative path
- pack name/type
- component names
- selected reference names
- demo category/path summaries

It does not intentionally include original official JSON source files, Python source scripts from official demos, textures, models, sounds, shaders, binary assets, or complete game data.

The public index may be incomplete, version-mismatched, or stale. Prefer locally generated indexes for accurate version-specific development.

## Trademarks And Ownership

Minecraft is a trademark of Mojang/Microsoft. NetEase Minecraft, MCStudio, and ModSDK materials are owned by their respective rights holders.

All third-party names, identifiers, and metadata are used only for compatibility, lookup, and developer education.

## User Responsibility

Users are responsible for:

- ensuring they have the right to access local game data or demo packs they index;
- complying with the terms that apply to official game data, demo packs, and documentation;
- verifying generated code against the target MCStudio/NetEase Minecraft version before release.
