# mc-be-hub-skills

一个安装包，五个 Minecraft Bedrock / 网易 MCStudio ModSDK 技能入口。日常开发、查询、检查与经验查阅集中在 `mc-bedrock-fast-code`，首次索引准备和资产工具按任务分开加载。

当前版本：**0.3.3**。

| 技能 | 用途 |
| --- | --- |
| [mc-bedrock-fast-code](skills/mc-bedrock-fast-code/SKILL.md) | 日常开发、官方查询、项目检查、经验记录与搜索 |
| [mc-bedrock-knowledge-setup](skills/mc-bedrock-knowledge-setup/SKILL.md) | 首次准备、明确更新或缺失索引恢复 |
| [mc-model-animation-to-blockbench](skills/mc-model-animation-to-blockbench/SKILL.md) | 模型、贴图与骨骼动画转 Blockbench，含复杂动作对照验收；体素 48/80/112/144 四档，默认 80，支持自定义 |
| [mc-shader-reconstruction](skills/mc-shader-reconstruction/SKILL.md) | 模型转 Shader、距离场/材质烘焙、刚体动画轨道编码、GLSL 与自动对照 |
| [mc-shader-offscreen-rendering](skills/mc-shader-offscreen-rendering/SKILL.md) | 桌面离屏关键帧、动画预览和 GPU 计时对比 |

## 一次安装全部技能

从 [Releases](https://github.com/Trryer/mc-be-hub-skills/releases/latest) 下载 `mc-be-hub-skills.zip`，或克隆本仓库。使用目录安装的客户端在解压后的仓库根目录执行：

```powershell
python -B scripts/install_skills.py --dry-run
python -B scripts/install_skills.py
```

安装器需要 Python 3.9 或更新版本。默认安装至 `$CODEX_HOME/skills`，未设置时为 `~/.codex/skills`；其他技能目录可显式指定：

```powershell
python -B scripts/install_skills.py --dest ~/.agents/skills
```

一次安装五个同级技能目录。同名技能先备份，再整体替换；备份位置写入安装报告。安装器不联网、不运行知识库准备、不安装转换依赖，也不修改现有知识数据。开启新会话查看五个技能，客户端未刷新时重启客户端。

## 插件安装

支持原生插件的 Codex CLI 可将本仓库登记为市场并安装整套技能：

```powershell
codex plugin marketplace add Trryer/mc-be-hub-skills
codex plugin add mc-be-hub-skills@mc-be-hub-skills
```

也可将已解压的套件目录登记为本地市场：

```powershell
codex plugin marketplace add C:/path/to/mc-be-hub-skills
codex plugin add mc-be-hub-skills@mc-be-hub-skills
```

本包包含根 `plugin.json`、`.codex-plugin/plugin.json` 和 `.agents/plugins/marketplace.json`。插件命令及市场是否可用取决于客户端版本；不支持时使用目录安装。插件安装与目录安装选择一种，避免同名技能被加载两次。插件方式已通过隔离 Codex CLI 安装检查，其他客户端界面需按其版本验收。

## 升级与首次准备

从旧版单技能升级时，直接安装整个套件；旧的 `mc-bedrock-fast-code` 同名目录会备份并替换，其他四个入口一并安装。技能源码维护在 `skills/` 下，统一发布一个 ZIP。

首次需要官方查询时调用 `mc-bedrock-knowledge-setup`，按指定来源准备索引；已有索引直接沿用。默认数据目录继续为 `~/.codex/mc-bedrock-fast-code-data`，查询与开发不会自动全量重建，也不因套件改名迁移数据。

[公开粗略索引](https://github.com/Trryer/mc-be-hub-skills/releases/latest/download/mc-bedrock-fast-code-public-index.zip) 是可选兼容资产，文件名沿用旧名称。它仅包含元数据，可能过时；优先使用本地生成的版本对应索引。详细说明见 [NOTICE.md](NOTICE.md)。

Blender、Open3D、ModernGL 等依赖只在对应转换或渲染任务需要时安装，按各技能的依赖清单与工作流执行。标准转换 CLI 可复用，但体素是近似重构，Blockbench 无顶点蒙皮，复杂动画仍需适配。精度和验收要求优先遵从用户；未指定时沿用各技能默认值。桌面离屏效果和计时不能替代游戏实测。

## 经验记录与搜索

支持按关键词查询已有记录、添加已确认的修复与验收结果，并配置记录目录。记录与技能安装目录分离，更新技能时继续沿用；命令和记录格式见[经验管理流程](skills/mc-bedrock-fast-code/references/experience-index.md)。

使用 `python -B scripts/package_bundle.py` 构建技能安装包。

## 校验与许可

```powershell
python -B scripts/validate_bundle.py
python -B -m unittest discover -s tests -v
```

完整套件验证需要 Python 3.11+ 及对应脚本依赖；检查结构、版本、链接、脚本、隔离安装和临时索引往返，不重建用户知识库或修改游戏。Windows 没有符号链接权限时，报告会明确该项未测试。

更新记录见 [CHANGELOG.md](CHANGELOG.md)，版本见 [VERSION](VERSION)。代码使用 [MIT License](LICENSE)。本项目与 Mojang、Microsoft、网易及 MCStudio 无隶属关系，第三方材料及公开索引边界见 [NOTICE.md](NOTICE.md)。
