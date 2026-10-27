# Changelog

## [0.3.2] - 2026-10-27

- 模型转 Shader 增加分部件距离场与刚体动画流程，明确绑定空间、适用的骨骼权重和变换条件。
- 新增刚体轨道编码 CLI：均匀采样矩阵转 RGBA8 动画纹理与 GLSL，支持可变部件/帧数、四元数连续性、位移范围及纹理预算检查。
- 动画验收增加原动作、整体旋转与叠加三种检查，以及全部轨道的量化误差和循环边界核验。
- 更新能力预览和工具边界；静态转换 CLI 继续输出静态或定格姿态，完整动画由独立轨道流程接入。

## [0.3.1] - 2026-10-27

- 新增经验管理 CLI，支持外部目录记录查询、搜索、添加和同名文件保护。
- 增加安装包构建工具与目录边界检查。
- 模型转换体素档位扩展为 48/80/112/144，默认 80；支持自定义精度与显式体素预算。
- 同步本地安装和能力入口。

## [0.3.0] - 2026-10-27

### 套件与安装

- 仓库及统一分发包更名为 `mc-be-hub-skills`，保留 Git 历史、旧版本及公开元数据索引。
- 一个套件提供五个技能入口：日常开发、知识库准备、模型与动画转 Blockbench、模型转 Shader、离屏渲染。
- 日常开发继续包含官方查询、项目检查和 Shader 实现经验；首次建立与维护索引移至独立技能，沿用现有外部知识数据目录。
- 增加插件清单、本地市场与一次安装五个目录的安装器，支持预演、旧目录备份、重复安装和失败回滚。
- 整合分发源码，移除旧单技能分发目录与安装 ZIP；本机实际安装的五个技能入口继续保留。

### 转换与经验

- 收录通用模型及骨骼动画转 Blockbench 的 CLI、贴图与动画烘焙流程；体素精度默认 80，保留 112 等显式选择。
- 模型转 Shader 提供静态网格/动画定格距离场、材质映射、GLSL 生成及自动对照 CLI，复杂骨骼动画仍按模型适配。
- 离屏渲染保留独立工具；日常开发包含经验查阅与积累入口。
- 修复新建包时 manifest 名称与实际包目录不一致的问题，保持包发现和检查规则一致。

### 验证与边界

- 增加清单/版本、相对链接、Python 语法与隔离安装检查，覆盖备份、幂等、错误路径拒绝和失败回滚。
- 继承包发现与项目检查的 10 项回归测试，并验证生成包、已有索引查询及临时 Demo/项目索引往返。
- Windows 无符号链接权限时对应安装测试标记为未测试；桌面离屏验证不替代 Minecraft 运行时和实际设备帧率验收。

## [0.2.0] - 2026-10-26

### 新增能力

- 模型转 Shader：读取 GLB、FBX、OBJ、Bedrock geo.json，按实际几何、层级、材质和动画进入 SDF 重建流程；不是一键无损转换。
- 精度遵循用户要求；未指定时默认性能优先。低精度案例仅记录典型流程，不作为复杂模型的精度上限。
- Shader 离屏渲染：随技能提供 Python 3 预览器及依赖清单，支持 PNG 关键帧、联系图、GIF、源码 SHA256 和桌面 GPU 计时报告。
- 增加经验查阅与积累模块。

### 整理与兼容

- 更新技能能力预览、路由和中英文说明，保留现有 API/事件查询、包生成、项目检查及按需知识库维护能力。
- 模型与离屏工作流均在 fast-code 内自包含；可选独立技能无需作为强制依赖，移除对本地兄弟技能路径及项目压缩包的依赖。
- 合并重复离屏记录并清理历史修改标记；安装包排除缓存、完整知识库、原始模型和游戏项目文件。
- 桌面离屏编译、画面与 GPU 计时只用于预览对照；目标游戏运行时、移动设备表现和实际 FPS 仍需游戏内验证。

### 验证

- Skill frontmatter 校验通过；47 处仓库相对链接有效，技能内部参考均位于安装包内。
- 既有包发现与检查测试 10 项通过，保留 ModSDK 开发能力。
- 使用随包预览器实际生成 160×90 的关键帧、联系图与 200 ms GIF；固定输入重复输出一致，时间变化产生预期画面变化，GPU query 报告成功。
- 示例在本机 NVIDIA 桌面驱动的 GLSL 100、300 es、330 包装下编译通过；这不是 MC 游戏内或移动设备验证。
- 安装 ZIP 与源码逐文件一致，CRC 检查通过；公开粗略索引沿用原资产，未重新抓取知识库。

## [0.1.8] - 2026-08-06

- Discover behavior and resource packs from manifest.json or pack_manifest.json within two directory levels instead of folder suffixes.
- Validate header.name against the containing folder and classify modules by data/resources.
- Support multiple behavior/resource packs and single-type projects.
- Reject missing, invalid, or duplicate header UUIDs across pack folders.
- Ignore routine studio.json changes in post-edit summaries.
- Add regression coverage for manifest discovery and lint failures.

## [0.1.7] - 2026-07-27

- Split Microsoft Learn and bedrock.dev knowledge setup into a dedicated on-demand workflow.
- Keep ordinary project editing and API lookup lightweight; knowledge checks are now explicit.
- Recognize both manifest.json and pack_manifest.json during project detection and linting.
- Include all four references/*.md workflow files in the source tree and install ZIP.

## [0.1.6] - 2026-07-27

- Crawl Microsoft Learn Creator and bedrock.dev stable/beta documentation with robots checks, retries, concurrent progress, and reusable page caches.
- Preserve raw HTML and JSONL while building compact metadata and an external SQLite search database.
- Query exact identifiers and format versions first, then weighted FTS5 and trigram indexes, with FTS4 and JSONL compatibility fallbacks.
- Add index-only rebuilds so search indexes can be regenerated without crawling either site.
- Keep downloaded documentation and generated SQLite databases outside the distributed skill package.

## [0.1.5] - 2026-07-12

- Route ordinary usage directly to project editing or API lookup workflows.
- Move first-time and maintenance knowledge preparation into a dedicated on-demand workflow.
- Add optional bounded subagent delegation for long setup and API research while keeping one owner for project edits.
- Preserve official docs, demo, installed vanilla, and authorized custom-project indexing capabilities.

## [0.1.4] - 2026-07-10

- Crawl official API, development-guide, and tutorial trees with scoped indexes.
- Search interface/event indexes first, then fall back across API types and broader documentation only when needed.
- Correct mirror API type labels from official interface/event paths.
- Preserve official Markdown return-value and remark sections in compact API indexes, including SpawnItemToPlayerInv inventory-capacity behavior.

## [0.1.3] - 2026-07-06

- Fix Python 2.7 runtime write behavior when appending zh_CN.lang entries.
- Verified bundled scripts with Python 2.7.18 at D:\\Programs\\Python\\Python2718.
- Re-tested create-pack, old behavior/resource suffix reuse, add-item, lint, and pyc cleanup.

## [0.1.2] - 2026-07-06

- Make bundled skill scripts Python 2.7/3 compatible with local compat helpers.
- Add JSONC-style // comment parsing for project JSON checks/indexes.
- Detect and reuse behavior/resource pack folders ending in beh/res/behavior/resource.
- Make Python 2.7.18 environment checks advisory instead of mandatory every run.
- Add Python syntax compile checker that removes generated pyc caches.
- Add private local custom project indexing and prioritize it during queries, with zh_CN.lang hits first.
- Search API update/deprecation notes when an API is missing from the main index.

## [0.1.1] - 2026-06-07

- Add ModSDK Python environment check for NetEase projects.
- Require/request Python 2.7.18 for syntax compilation checks, with fallback guidance when unavailable.
- Check and install mc-netease-sdk under Python 2.7.18.
- Avoid false-positive project detection for the skill package scripts.

## [0.1.0] - 2026-06-06

Initial open-source release. Includes the Codex skill package and a lightweight public metadata index fallback. The public index is metadata-only and does not include official Minecraft/NetEase assets, original demo source files, or full game data.
