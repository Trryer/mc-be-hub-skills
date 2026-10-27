# 私有经验记录能力

公开技能提供记录、搜索和复用流程。用户积累的具体问题、修复、验证结果、截图和日志存放在技能目录之外；安装或更新技能不覆盖它们。

## 存储与查询

默认记录目录为 `~/.codex/mc-bedrock-fast-code-data/private/experience/mc-be-hub-skills`。可通过 `MC_BE_EXPERIENCE_ROOT` 环境变量或 CLI 的 `--root` 指向自己的记录库。存储路径不能位于公开套件或已安装技能内。

```text
python scripts/experience.py path
python scripts/experience.py list
python scripts/experience.py search "当前问题的关键词"
python scripts/experience.py --root <私有记录目录> search "关键词"
```

目录不存在时视为尚无记录，继续查当前项目和官方接口。目录存在时先搜关键词，再读命中的少量文件；核对记录适用版本、证据和当前源码，确认仍适用后再采用。

## 记录已确认结果

将下列空白格式填入本地 UTF-8 文件，区分用户确认、游戏内验证、桌面检查和未测项：

```markdown
## 适用范围
版本、平台和必要环境。

## 现象与复现
触发条件、预期与实际结果。

## 原因及修复
已核实的原因、修改位置和方案。

## 验证与边界
实际执行的检查、结果、证据路径和未覆盖范围。
```

```text
python scripts/experience.py add --slug <英文短名> --title "问题标题" --body-file <填写后的本地文件>
```

同名记录已存在时不会覆盖。需要维护既有记录时直接编辑私有记录文件，保留有用证据，避免将猜测写成已确认经验。

## 云端同步与分发

GitHub 的可见性以仓库为单位。云端记录放在独立的 **private 仓库**中，可在该仓库内建立 `experience/` 专用文件夹；公开仓库中的 `private/` 文件夹和 `.gitignore` 都不提供访问控制。

用户要求同步时，先核实目标仓库确为 private，再只提交相应记录和所需证据。此脚本只操作本地文件，不会联网或自动推送。

公开源码、Git 历史、标签快照和 Release 压缩包仅包含通用能力。使用套件的 `scripts/package_bundle.py` 打包；具体记录不进入公开源码或分发包。已误公开时同时处理历史和旧附件，删除最新工作区文件不足以撤回旧版本；已下载副本无法远程撤回。
