# Cuboid 导入与距离场图集校验

用于直接读取 `.bbmodel`、转换 Bedrock cube，或为自定义距离场适配器检查采样常量。GLB/FBX/OBJ 的内置 CLI 继续沿用原有入口；本检查不增加它的输入格式。

## 导入后先验证几何

1. 读取 `.bbmodel` 的 `meta.model_format`，确认该格式的轴向、枢轴和欧拉角顺序。Bedrock 格式在 Blockbench 中使用 `ZYX`；按列向量约定，旋转矩阵为 `Rz @ Ry @ Rx`。`XYZ` 为 `Rx @ Ry @ Rz`，有两个以上非零旋转分量时通常不同。顺序应从目标 Blockbench 的 `Format.euler_order` 核验，不能根据三元素数组的存储顺序推断，也不能套用 Blender 的默认欧拉约定。
2. cube 自身旋转、父 bone 链及每层 pivot 都须应用。Blockbench 5 的组属性可放在顶层 `groups` 中，`outliner` 只保存 UUID 与树结构；先按 UUID 关联组定义，再遍历父链。旧格式组属性内联时保留相应读取分支。
3. Bedrock `.geo.json` 导出具有自己的坐标反射与角度转换约定；直接读 bbmodel 与读导出的 geo 是两条输入路线，分别校验转换，不在未经确认的情况下重复翻轴。
4. 建立一个**独立于自写导入器**的参考。可在隔离的原生 Blockbench 实例中加载源文件，调用 `Canvas.updateAll()` 并更新世界矩阵后读取 `cube.getGlobalVertexPositions()`，或导出原生几何作为参考。比较每个 cube 的变换后角点、尺寸及代表视图，优先覆盖多轴旋转、非零 pivot 和父层级组合。

统计 cube/三角面数只能发现数量遗漏；全部元素都存在，仍可能被错误旋转或移位。总包围盒也可能几乎一致。若差异在导入后的参考网格就已经存在，先修导入变换并重烘焙，增加体素分辨率或 raymarch 次数无法修复错误的几何位置。

## 图集布局必须与部署采样器一致

烘焙元数据是布局来源，生成采样常量时直接使用同一份元数据。核验：

- 体素维数、切片轴、原点、步长及采样点是 cell center 还是 grid vertex。
- PNG 实际宽高、每行列数、行数、瓦片尺寸、边缘 padding 与有效切片数。
- 距离符号/量程/量化编码、UV/材质的通道约定，以及贴图绑定到的 sampler。
- 纹理方向、数据纹理的色彩空间、过滤、mipmap 和引擎实际上传行为。

距离与 UV/颜色使用同一布局时，共用布局常量或生成同值常量；若刻意使用不同分辨率，各自保存并核验完整布局。更新了 atlas 排列而保留旧材质采样列数，会读到别的切片、padding 或空瓦片，表现为串色、黑带，甚至看起来像模型部件消失。

### 可执行常量检查

`scripts/check_shader_contract.py` 只依赖 Python 标准库。自定义适配器提供“GLSL 常量名 → 烘焙 JSON 路径”的小型契约文件，可同时检查多个采样器和 PNG 尺寸。例如烘焙元数据的 `uv_atlas` 对象具有 `cols/w/h/tile_w/tile_h/dims` 字段：

```json
{
  "metadata": "field.json",
  "constants": {
    "UV_COLUMNS": "uv_atlas.cols",
    "UV_RESOLUTION": ["uv_atlas.w", "uv_atlas.h"],
    "UV_TILE": ["uv_atlas.tile_w", "uv_atlas.tile_h"],
    "UV_GRID": "uv_atlas.dims"
  },
  "textures": [
    {"file": "textures/uv.png", "size": ["uv_atlas.w", "uv_atlas.h"]}
  ]
}
```

```powershell
python scripts/check_shader_contract.py --contract adapter-contract.json --shader deployed.fragment --out contract-report.json
```

相对资源路径以契约文件所在目录为基准；字段名按实际元数据调整。支持数字、向量构造和常量别名；宏分支中的同名定义、任意算术表达式等会明确拒绝，需先选定实际部署分支或用 GLSL 工具求值。检查输出保留源码与元数据摘要；不一致、缺常量或缺资源均返回非零退出码。PNG 检查只读取文件头中的尺寸，不检查完整解码、纹理内容、sampler 绑定或 GPU 上传结果。

## 分开定位“几何缺失”与“材质发黑”

使用相同模型空间、镜头和输入，分别比较：

1. **源几何与 shader 的纯色命中遮罩**：排除光照和贴图，检查真正的轮廓、孔洞与缺面。独立原生参考可发现导入错误；从错误中间网格生成的参考只能证明烘焙与该网格一致。
2. **不带光照的 UV/基础色**：遮罩有该部位而基础色错误时，检查切片定位、UV、贴图方向和绑定。
3. **完整着色**：只有这一步出现偏差时，再检查法线、阴影、AO、曝光与合成。

代表视角覆盖正反、侧面与顶部；只看正面可能掩盖部件被转到错误方向的问题。修布局后重测材质，修导入后重新烘焙并复查几何、材质与动画。发现两类错误时分别记录，避免用材质修复的截图宣称几何也已正确。

格式依据可查 Blockbench 官方源码：`js/formats/bbmodel.js`、`js/outliner/types/cube.js` 及目标版本的 Bedrock 格式定义；用实际安装版本的加载结果交叉验证。
