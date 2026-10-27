# 预览契约与验证范围

## 环境

使用独立 Python 3 环境；依赖列于 requirements-preview.txt。需要桌面 OpenGL 驱动和可创建 standalone context 的 ModernGL 环境。Python 运行环境与 ModSDK 行为包分开。

    python -m venv .venv-shader-preview
    .venv-shader-preview\Scripts\python.exe -m pip install -r <mc-shader-offscreen-rendering>/references/requirements-preview.txt

## 输入契约

脚本读取实际 fragment 文件并生成 SHA256。支持的输入应满足：

- 以 Minecraft multiversion 风格编写，并通过 fragmentVersionCentroidUV.h 使用 uv。
- 用 EXTRA_VECTOR1 = (elapsedSeconds, screenWidth, screenHeight, exposure) 传入时间、视口和曝光。
- 输出使用 gl_FragColor。

预览器只替换上述引擎 include，并添加最小桌面 GLSL 版本包装。任何其他 include、额外活跃 uniform、sampler、游戏纹理绑定或不同参数布局都要扩展适配；缺少必需输入时应明确报错，而非产出误导图像。

## 常用命令

    python <mc-shader-offscreen-rendering>/scripts/render_sdf_preview.py --shader <deployed-fragment> --out <validation-dir>

多关键帧及原生目标分辨率：

    python <mc-shader-offscreen-rendering>/scripts/render_sdf_preview.py --shader <deployed-fragment> --out <validation-dir> --width 1920 --height 1080 --times 0 1 2.5 4 5

五秒、30 FPS GIF：

    python <mc-shader-offscreen-rendering>/scripts/render_sdf_preview.py --shader <deployed-fragment> --out <validation-dir> --gif --fps 30

可选项见 --help。默认时长 5 秒，默认关键帧为时长的 0%、18%、29%、54%、65%、99%；默认曝光 1.15，GPU query 样本 5 次。contact sheet 与 GIF 使用缩图，GIF 最长边不超过 640 像素。实际渲染分辨率和编码尺寸应分别记录。

## 判读与复现

先记录用户指定的画面、时间段、分辨率和性能标准；可提示用户补充，未指定则执行以下默认复查，继续工作而不新增确认步骤。

- 实际打开关键帧和联系图，检查构图、颜色、裁切与指定效果；有运动时查看连续预览，覆盖关键时刻和循环边界。图片非空或编译成功只算初步检查。
- 默认要求无未解释的黑屏、缺失输入、非有限像素、时间跳变或重复输入不稳定；预期黑场、随机效果等按已记录的效果契约检查。
- 有源模型或参考画面时，在相同镜头、姿态和着色条件下并排比较；模型精度阈值由模型重建任务的标准决定，此通用预览器不替用户决定还原精度。
- 发现偏差先核对实际部署源码、宏、参数和纹理，再修正并重跑受影响检查；改源码或输入后生成新证据，旧报告不代表新版本。
- 保存关键帧、连续预览和报告，逐项标注通过、失败、未测及不适用；记录实际输入与测量条件。无法验证的游戏行为明确列为待验。

检查 shader 编译、输出是否有限且非空、时间是否驱动预期区域、重复渲染是否稳定，以及首尾画面和目标画幅是否合适。动画预览要覆盖动作关键时刻与镜头速度边界；静态模型和固定相机在没有时间性材质时，应在不同采样时间输出相同图像。

先 warm-up 再用 GPU time query 重复测量，在相同分辨率、宏、参数、相机、姿态和纹理下比较。记录 GPU/驱动信息、shader SHA256、GLSL wrapper、分辨率和样本统计。桌面 GPU query 不含 framebuffer readback、PNG/GIF 编码、纹理上传或 MC 合成开销；CPU 墙钟计时应显式同步 GPU，并标注测量边界。

GIF 每帧时间以 10ms 为单位。按累计帧边界分配时长以减小量化误差；记录输入采样数和编码器实际帧数，因为相同帧可能被合并。

此工具不模拟 Minecraft 的材质发现、pass 顺序、引擎 include、游戏纹理绑定、深度合成、移动 GPU 或整体帧率。最终兼容、视觉与性能结论必须在目标游戏运行时验证。
