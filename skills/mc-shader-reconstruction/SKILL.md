---
name: mc-shader-reconstruction
description: "将 GLB/glTF、FBX、OBJ 或 Bedrock geo.json 模型重建为 Minecraft ModSDK shader；内置静态/定格距离场转换、材质映射、刚体动画轨道编码和对照验收工具，复杂动画按部件与源数据适配。"
---

# Minecraft 模型转 Shader

根据源模型和用户精度要求生成 MC ModSDK 可接入的 shader。先读[默认验收标准](references/acceptance.md)，记录用户标准或默认标准。

## 选择工作路线

- **静态 GLB/glTF、FBX、OBJ，或动画的指定姿态**：优先运行内置[通用转换 CLI](references/automated-pipeline.md)。它统一坐标、烘焙距离/法线/原 UV 材质、生成模型空间 GLSL 与全屏适配器，并用原三角网格自动对照；无需逐模型重写烘焙器。先使用 `--inspect-only` 核对导入信息，再转换。
- **复杂网格需要原动作，且部件是单骨骼或节点刚体驱动**：按[分部件距离场与刚体动画](references/rigid-part-animation.md)烘焙绑定几何与独立轨道；内置 CLI 可编码已求值的动作矩阵，导入、拆件与游戏接入仍需适配。静态距离场不会自动生成完整动画。
- **设备预算很紧或需要少量程序几何**：按[解析 SDF 方法](references/reconstruction.md)适配；源数据导入和坐标归一化可复用 CLI 中间结果。
- **Bedrock geo.json**：读取 bone/cube/pivot 与动画，走解析 SDF 路线；当前 CLI 不直接读取此格式。
- **Cuboid bbmodel 或自定义图集适配器**：按[导入与图集校验](references/import-and-atlas-checks.md)核对格式旋转顺序、父链和部署采样常量；bbmodel 先经独立原生参考验证，再进入重建，当前转换 CLI 不直接读取此格式。
- 用户目标为普通网格显示时，使用项目已有几何渲染路线。

采样距离场的低档也不保证比解析 SDF 更省性能。依据目标设备和实测成本选择路线；不承诺一键无损转换。

## 精度与性能

用户明确指定模型精度、设备或帧率预算时按要求制作。未指定时性能优先：自动路线从 low 开始，按实测成本决定是否改用解析 SDF；解析路线用少量基本体、局部坐标、镜像和有限重复保留主要轮廓。控制步进、阴影、AO 和高频细节，并说明简化项。高精度按需提高采样或增加必要的 SDF 部件、负空间和材质差异，再测量影响；不能把旧案例的低细节当成精度上限。

## 执行流程

开始每次重建前必须读取[默认验收标准](references/acceptance.md)：记录用户标准或默认标准，可提示用户补充；交付前实际查看对照图和连续预览，失败项修正后复测。

1. 盘点模型实际数据：对象和骨骼、三角形或 cube 数、包围盒、单位、轴向、父子变换、材质、贴图和动画轨道。文件扩展名不能代替内容检查。
2. 建立统一坐标映射。先应用父级、旋转与缩放，再将所有部件、pivot、动作和包围体转换到同一模型空间，并记录轴向和比例。
3. 自动路线按精度和预算运行 CLI，检查 `report.json`；缺图、缺 UV、透明材质、超预算和验收失败必须明确处理。解析路线写出部件与动作计划，先对照灰模再补精度。
4. 自动路线实际查看并排图和连续预览，按模型增加顶底或关键视角；解析路线实现分组 SDF、稳定步进和材质。所有姿态计算共享变换。失败后修正复测。
5. 按 [MC 接入流程](references/mc-integration.md) 为新 shader 配置独立资源和生命周期，并按[游戏内验证](references/game-validation.md)检查实际画面和帧率。
6. 按验收标准逐项复查实际部署结果，保存证据；交付重建/省略结构、已通过检查、失败项、未测项及复现方式。`AUTOMATED_PASS` 仅为自动桌面检查通过，人工视觉、Minecraft 运行时与用户确认分别记录。CLI 不自动修改游戏包。

## 实现约束

- 对高面数网格按结构拆件；不要把所有三角形或 cube 直接展开成巨大的逐面 GLSL 循环。
- 全局与部件包围体要覆盖所有静态几何及动画轨迹；薄板、孔隙和掠射角需要单独检查。
- 刚体变换使用统一矩阵约定。非均匀缩放和形变会改变距离界，应按保守步长处理。
- GLB、FBX、OBJ 的材质和动画能力取决于具体导入器及文件。OBJ 需要检查 MTL 和贴图；FBX 需核验 ASCII/二进制与版本；转换成功也不等于已生成 MC shader。
- MC 侧使用目标项目支持的 GLSL 语法和 Python 运行时。桌面工具或文件解析依赖不能放进 ModSDK 行为包。

更多几何拆分、坐标统一、动画映射和距离场取舍见[模型重建方法](references/reconstruction.md)。God Eye 与 Kyushu 只提供低精度实现的典型流程，见[代表性流程](references/implementation-patterns.md)及[工具与案例](references/tools-and-cases.md)。
