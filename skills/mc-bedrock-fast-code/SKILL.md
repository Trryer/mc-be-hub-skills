---
name: mc-bedrock-fast-code
description: "网易 Minecraft Bedrock/MCStudio ModSDK 日常开发：修改项目、生成包和资源、查询官方 API/事件/原版数据、检查代码，以及查询和积累外部私有经验记录。索引首次建立与维护交给 mc-bedrock-knowledge-setup。"
---

# Minecraft Bedrock 日常开发

这是 `mc-be-hub-skills` 的主要开发入口。开发、查询、检查和实现经验在此；知识库建立、模型转换和离屏工具各有独立入口。先处理用户要改的项目，不在日常开发前运行安装或索引维护流程。

## 按任务读取

- **修改项目、生成包/物品/方块/实体/UI、排查代码或资源引用**：读[项目开发与检查](references/project-editing.md)，使用本技能的脚手架、检测与检查工具。
- **API、事件、返回值、官方资源名或 JSON 规范**：读[查询流程](references/api-search.md)，直接查已有索引；按需查接口返回值和备注。
- **制作或修改 Shader**：先读[验收与交付检查](references/shader-validation.md)。
- **查已有经验或记录已解决的问题**：读[私有经验记录流程](references/experience-index.md)，按任务搜索外部记录库。公开技能只提供管理能力与空白格式，具体记录存放在技能目录外。

## 套件内其他入口

| 任务 | 技能 |
| --- | --- |
| 首次准备知识库、明确更新/修复索引、必需索引缺失 | [mc-bedrock-knowledge-setup](../mc-bedrock-knowledge-setup/SKILL.md) |
| 通用模型与动画转 Blockbench | [mc-model-animation-to-blockbench](../mc-model-animation-to-blockbench/SKILL.md) |
| 模型转 Shader、距离场与刚体动画轨道、对照验收 | [mc-shader-reconstruction](../mc-shader-reconstruction/SKILL.md) |
| Shader 关键帧、旋转/动画预览与桌面 GPU 对比 | [mc-shader-offscreen-rendering](../mc-shader-offscreen-rendering/SKILL.md) |

普通查询无结果时先核对术语、来源和查询条件；无结果本身不表示需要重建索引。只有必需来源的索引确实缺失，才转到索引技能补建该项。开发不依赖缺失来源时继续工作并说明限制。

## 项目约定

- 遵守项目 AGENTS.md，保留用户未关联改动；结构查询优先用 codebase-memory，覆盖缺口或字面量再读源码。
- 从 studio.json 与 pack_manifest.json/manifest.json 确认包；用户的 qs/qe 标记只用于指定行为包/资源包源码，技能与文档直接修改。
- 使用实际命名空间、资源 ID 和已核实 API；读取官方返回值和备注后再写判空/兼容逻辑。
- 生成资源前确定项目、命名空间和本地 ID；按项目既有结构生成，相关结构变化后运行检查。
- 日常查询继续使用现有 `~/.codex/mc-bedrock-fast-code-data/knowledge_registry.json`；套件改名不迁移或重建用户数据。
- Shader 画面、编译、桌面预览、Minecraft 运行时与用户验收分别记录；仅加载当前任务需要的经验。
- 具体经验及其截图、日志、项目细节属于私有数据；云端同步使用独立私有仓库，不能靠公开仓库中的文件夹名实现保密。发布只打包通用功能，检查源码、Git 历史和 Release 附件的边界。
