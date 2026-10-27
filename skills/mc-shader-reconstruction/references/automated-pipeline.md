# 通用模型转 Shader：可执行管线

## 适用范围与原理

入口是 `scripts/model_to_shader/convert.py`，所有脚本、GLSL 模板和依赖清单均随技能分发。换模型主要替换输入、贴图、精度与预算参数，代码没有项目路径、模型名或特定网格结构依赖。

固定流程：导入并应用节点世界变换 → Y 向上、XZ 居中、底面 Y=0、最长边=2 → 最近三角面距离/重心 UV/法线采样 → 两张带 padding 的 2D atlas → 模型空间 GLSL → 源三角网格对照与旋转预览。

封闭网格用射线奇偶求内外符号；开放/非流形网格使用薄表面壳，报告实际路径。采样会产生分辨率误差，薄片、尖角、狭孔和贴图接缝尤其需要复查。形状差异由数据处理，语义拆件、艺术取舍和动画适配仍由需求决定。

## 本地安装

建议主环境用 64 位 Python 3.11/3.12、Blender 4.5；Open3D 和 OpenGL 驱动必须可用。PowerShell 中，在技能根目录运行：

```powershell
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r ./scripts/model_to_shader/requirements.txt
```

Blender 自带 Python 也需要 numpy、Pillow；主环境装包不等于 Blender 自带解释器已装包。用实际 Blender 目录中的解释器执行 `-m ensurepip`，再 `-m pip install numpy Pillow`。

ASCII FBX 使用独立 Python 3.11 环境：

```powershell
py -3.11 -m venv .fbx-venv
& ./.fbx-venv/Scripts/python.exe -m pip install -r ./scripts/model_to_shader/requirements-fbx.txt
```

此解释器用 `--fbx-python` 指定，独立子进程隔离原生包装器和不同 Python 的 numpy 环境。二进制 FBX 默认由 Blender 读取；ASCII FBX 自动走 ufbx，也可显式指定 reader。依赖通过本机安装获得，不依赖旧项目、素材 ZIP 或其他技能。

## 运行

先核对导入，再生成，每次使用新的输出目录：

```powershell
& ./.venv/Scripts/python.exe -B ./scripts/model_to_shader/convert.py C:/assets/model.glb C:/output/model-inspect --blender C:/Blender/blender.exe --inspect-only
& ./.venv/Scripts/python.exe -B ./scripts/model_to_shader/convert.py C:/assets/model.glb C:/output/model-medium --quality medium --blender C:/Blender/blender.exe
& ./.venv/Scripts/python.exe -B ./scripts/model_to_shader/convert.py C:/assets/model.fbx C:/output/model-fbx --quality medium --reader ufbx --fbx-python ./.fbx-venv/Scripts/python.exe --albedo C:/assets/color.jpg
```

GLB/glTF、OBJ+MTL 和二进制 FBX 走 Blender。OBJ 默认 Y 向上、前向 -Z；源约定不同则设置 `--obj-up`/`--obj-forward`，二者必须是不同轴。Blender 负责源格式到内部轴向映射，适配器再统一模型空间。完整父子变换、负尺度绕序、非均匀尺度的法线逆转置、多 Mesh、多材质和逐面角 UV 接缝由代码处理。

材质自动读取基础色贴图或常量，支持标准 glTF 基础色乘数；复杂节点图先烘焙。`--albedo` 是用户明确指定的全材质 RGB 覆盖，保留原 UV；`--material-map` 是 JSON 对象“源材质名 → 图片路径”，相对路径从 JSON 所在目录解析。未知材质名、缺文件、纹理网格缺 UV 都会报错。

有有效动画时要求显式选择姿态：Blender 路径用 `--pose-frame` 读取当前导入场景时间轴；ufbx 路径可用 `--clip NAME --pose-frame 10 --pose-fps 30`，从片段起点取 10/30 秒并求值蒙皮。多个 FBX 片段必须选定一个。不同导入器会给时间轴添加不同的起始帧偏移，跨工具比较时核对实际片段时间，而不是只比较帧号。**输出是静态姿态**，生成的旋转仅是整体模型旋转；当前代码不输出整段骨骼动画播放。

全部参数以 `convert.py --help` 为准。`--headers` 可指定真实引擎 GLSL 头目录，`--glslang` 可指定严格编译器；缺少这些可选参数时，报告区分桌面包装编译与引擎头检查。

## 精度和预算

| 档位 | 最长网格边默认采样数 | 最大步数 | 用途 |
| --- | --- | --- | --- |
| low，默认 | 128 | 160 | 性能优先的起点 |
| medium | 256 | 224 | 增加轮廓与材质细节 |
| high | 512 | 384 | 高精度采样，需检查显存与纹理尺寸 |

`--resolution` 与 `--steps` 可独立覆盖采样和步进，不会降低所选精度的验收阈值。默认工程阈值见[验收标准](acceptance.md)。用户标准优先，报告记录实际阈值；失败后先修转换或采样，不能为了通过而降低阈值。

分配前检查 atlas 最大边和两张 RGBA8 atlas 的解码显存预算，默认分别为 8192 和 256 MiB。高档、接近立方体的体积通常超过默认预算；先看报错中的实际尺寸/内存，再按用户设备决定降采样、拆分或显式提高 `--max-atlas`/`--max-mib`。CPU 内存还包括原网格、索引和采样临时数组，预算不是整个进程内存上限。PNG 文件小不代表 GPU 成本低。

## 输出与复用契约

- `intermediate/mesh.npz`、`scene.json`、PNG：版本 1 中间格式。顶点、三角面、逐面角法线/UV、逐面材质和归一化记录。新增导入器满足 `common.save_scene()` 契约，即可复用后续管线。
- `textures/field.png`：RG 编码 uint16 距离，BA 编码八面体法线；作为数据纹理上传，避免 sRGB 解码、压缩、翻转或 mipmap 改变数值。
- `textures/material.png`：RGB 基础色，A 固定 255。
- `field.json`：网格原点、步长、维数、atlas 排列、距离范围、符号策略、内存和资源摘要。
- `model.glsl`：`msTrace`、`msNormal`、`msSample` 等模型空间函数。输入射线方向归一化；距离和位置使用统一模型单位。当前函数前缀为 `ms`，同一 shader 合并多个模型需适配命名。
- `<name>.fragment/.vertex`：独立全屏旋转适配器；`EXTRA_VECTOR1=(秒数,宽,高,每秒角度)`。
- `integration.json`：参数、纹理槽和接入契约。两张 atlas 绑定槽 3/4，双线性、Clamp、无 mipmap；实际 MC 材质与纹理管线仍须验证。
- `validation/`：四方向原网格图、结果图、各自遮罩、并排图、48 帧旋转 GIF、编译与桌面 GPU 计时。
- `report.json`、`import.log`：状态、源模型摘要、导入/烘焙/验收结果及错误。

原网格参考用 Open3D 射线与原三角形求交，使用原 UV、法线、贴图和相同光照，独立于距离场求交。它与转换共享导入器，所以能检查“导入结果 → shader”，不能独立证明导入结果与 DCC 原文件完全一致。指标不覆盖所有角度和小部件，实际打开并排图、旋转预览并按模型补测。

## 状态与边界

| 状态 | CLI 退出码 | 含义 |
| --- | --- | --- |
| `INSPECTED` | 0 | 导入检查完成 |
| `AUTOMATED_PASS` | 0 | 自动编译/桌面对照通过 |
| `BUILT_UNVALIDATED` | 0 | 显式 `--no-validate`，尚未验收 |
| `ERROR` | 1 | 参数、导入、材质、预算或执行失败，查看报告 |
| 不覆盖现有非空输出 | 2 | 保留原目录内容 |
| `VALIDATION_FAILED` | 3 | 资源已生成，但指标未通过 |

人工视觉默认 `PENDING`，`minecraft_runtime_tested=false`；自动通过不会改变这两项。透明混合/裁剪、复杂程序材质、全 PBR、实时蒙皮/形变和 geo.json 自动读取目前不在 CLI 范围。ufbx 适配器要求已三角化的 FBX；非三角二进制 FBX 可改用 Blender，ASCII 文件先在 DCC 三角化导出。法线贴图/发光等省略项记入报告，复杂材质显式拒绝而不静默猜测。

CLI 负责模型资源，不自动部署包或生成游戏命令。接入时沿用[MC 模型接入流程](mc-integration.md)，验证运行时资源与生命周期。

## 可重复验证工具

完整刚体动作可继续进入[分部件动画流程](rigid-part-animation.md)。`rigid_animation.py` 复用已求值的矩阵数据输出动画纹理和 GLSL；它不会改变本静态转换 CLI 的动画范围。

`make_regression_assets.py` 在 Blender 中现场生成多网格、UV 接缝、多材质、父变换、负/非均匀尺度和骨骼动画夹具。`run_regression.py` 调用公开 CLI，验证跨格式输出与错误分支；夹具不是按模型手写 shader 的案例。

```powershell
& ./.venv/Scripts/python.exe -B ./scripts/model_to_shader/run_regression.py --blender C:/Blender/blender.exe --fbx-python ./.fbx-venv/Scripts/python.exe --work C:/output/model-shader-regression
```

检查回归报告、实际图像和目标模型；工具回归不替代目标模型验收。
