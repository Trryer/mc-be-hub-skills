---
name: mc-bedrock-knowledge-setup
description: "首次安装时准备 Minecraft Bedrock/网易 ModSDK 知识库，或在明确更新、修复及必需索引缺失时维护 API、文档、原版、Demo 和自定义项目索引。日常查询使用 mc-bedrock-fast-code 的已有索引。"
---

# 知识库初始化与索引维护

这是 `mc-be-hub-skills` 中低频使用的索引入口。安装套件只安装技能，不自动联网下载文档或重建索引。通常首次安装准备一次；以后仅在用户要求更新、来源版本变更、损坏或必需索引缺失时维护。

## 选择范围

1. 确定本次需要的来源、目标版本和外部数据根目录。默认沿用 `~/.codex/mc-bedrock-fast-code-data` 与其中的 `knowledge_registry.json`，保留现有数据。
2. 用[只读状态检查](scripts/knowledge_status.py)检查本次需要的键，例如 `python scripts/knowledge_status.py --require api_references`。已有且可读时直接复用；状态检查不重建索引，也不要求其他来源全部齐全。
3. 网易 API、指南、教程、原版、Demo、自定义索引读[初始化与维护](references/knowledge-setup.md)；Microsoft/bedrock.dev JSON 文档读[JSON 文档索引](references/microsoft-json-setup.md)。只处理选定来源；原版需明确安装路径和版本，自定义项目需有授权范围。
4. 执行对应脚本，保留日志。验证要求的键和文件；SQLite 来源检查完整性；至少进行一次有代表性的查询。说明更新范围、复用内容和失败项。

日常开发与查询用[主技能](../mc-bedrock-fast-code/SKILL.md)。首次安装说明与查询失败消息都不能解释为“每次使用前检查所有索引”。

## 数据与分发

原始文档、数据库、下载缓存和私有项目索引放在用户外部数据目录，不写进技能发布包。更新工具与更新知识数据是两件事：升级套件不会清空旧数据库。
