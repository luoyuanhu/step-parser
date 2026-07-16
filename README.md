# step-parser

**Pure Python STEP File Parser for Sheet Metal Geometry Extraction**

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/pypi-step--parser-orange.svg)](https://pypi.org/project/step-parser/)

Parse ISO 10303-21 (STEP P21) CAD files with **zero external dependencies**. Extracts BREP geometry — bounding box, surface area, holes, bends, thickness — from STEP files exported by all major CAD systems.

📦 `pip install step-parser` · 🐍 Python 3.9+ · 🪶 Pure standard library

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Format Support** | STEP AP203, AP214, AP242 (ISO 10303-21 P21 ASCII) |
| **CAD Compatibility** | Creo, SolidWorks, NX, CATIA, Inventor, FreeCAD, Solid Edge, Fusion 360, Onshape |
| **Assembly** | Multi-part assembly tree, instance counting, PRODUCT→CLOSED_SHELL chain tracing |
| **Geometry** | Bounding box, surface area, blank area, outer profile cutting length, perimeter |
| **Sheet Metal** | Hole inventory (by diameter), pierce count, bend detection, thickness estimation |
| **Validation** | Pre-parse file validation — entity statistics, CAD source detection, problem diagnosis |
| **2D Contour** | Extract outer profile + inner holes in local 2D coordinates |

---

## Quick Start

### Installation

```bash
pip install step-parser
```

### 3-Line Example

```python
from step_parser import parse, analyze, extract_assembly

store = parse('part.stp')                          # Parse STEP file
assembly = extract_assembly(store)                 # Get parts list
result = analyze(store, assembly['parts'][0])      # Compute geometry
print(result['name'], result['bbox_mm']['label'])  # → "BRACKET" "120.5×80.3×2.0"
```

### Command Line

```bash
# Parse and print geometry report
python -m step_parser part.stp
```

---

## Usage Guide

### Validate before parsing

```python
from step_parser import validate

report = validate('part.stp')
print(report['status'])      # 'ok', 'warn', or 'fail'
print(report['info'])        # File name, CAD source, schema, units
print(report['stats'])       # Entity counts by type
print(report['warnings'])    # Potential issues (non-solid, faceted, etc.)
```

### Parse and extract assembly

```python
from step_parser import parse, extract_assembly

store = parse('assembly.stp')

# Entity store with lazy parsing and reference graph
print(f"Parsed {len(store._entities)} entities")
print(store.get_type(123))        # Get entity type by ID
print(store.get_args(123))        # Get parsed arguments (lazy)

# Extract assembly tree
assembly = extract_assembly(store)
for part in assembly['parts']:
    print(f"{part['name']}: {part['instances']} instances, shell_id={part['shell_id']}")
```

### Analyze geometry

```python
from step_parser import analyze

for part in assembly['parts']:
    result = analyze(store, part)

    # Bounding box
    print(result['bbox_mm'])           # {'width': 120.5, 'depth': 80.3, 'height': 2.0}

    # Surface & blank area
    print(result['surface_area_m2'])   # 0.0213 m²
    print(result['blank_area_m2'])     # 0.0095 m²

    # Holes by diameter
    for h in result['holes']:
        print(f"Ø{h['diameter_mm']}mm × {h['count']}")

    # Manufacturing features
    print(f"Bends: {result['bend_count']}")
    print(f"Pierce holes: {result['pierce_count']}")
    print(f"Thickness: {result['thickness_mm']} mm")
    print(f"Type: {result['type']}")   # 'flat' or 'bend'
```

### Low-level API — direct BREP access

```python
from step_parser import collect_shell_geometry, classify_faces, get_loop_edges, compute_face_area

geom = collect_shell_geometry(store, shell_id)
faces = classify_faces(store, geom['face_ids'])

for face in faces:
    area = compute_face_area(store, face)
    edges = get_loop_edges(store, face['outer_loop_id'])
    print(f"{face['surface_type']}: area={area:.1f}mm², edges={len(edges)}")
```

---

## CAD System Compatibility

Tested with STEP exports from:

| CAD System | Format | Notes |
|------------|--------|-------|
| **Creo Parametric** (PTC) | AP203/AP214 | PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE |
| **SolidWorks** (Dassault) | AP203/AP214 | Standard PRODUCT_DEFINITION_FORMATION |
| **NX** (Siemens) | AP203/AP214 | Standard entity naming |
| **CATIA** (Dassault) | AP203/AP214 | May use different unit systems |
| **Inventor** (Autodesk) | AP203/AP214 | Standard |
| **FreeCAD** | AP203/AP214 | Uses Open CASCADE exporter |
| **Solid Edge** (Siemens) | AP203/AP214 | Standard |
| **Fusion 360** (Autodesk) | AP203/AP214 | Standard |
| **Onshape** (PTC) | AP203/AP214 | Standard |

**Important**: File must be exported as **BREP** (exact geometry), not faceted/tessellated mesh. Faceted files (STL-converted STEP) will be flagged in validation but may still produce reduced-accuracy results.

---

## What This Library Does NOT Do

- ❌ Does not render 3D graphics (use [occt-import-js](https://github.com/kovacsv/occt-import-js) or Three.js for web, pythonocc for desktop)
- ❌ Does not modify or write STEP files (read-only parser)
- ❌ Does not do CAM toolpath generation
- ❌ Does not include pricing/quotation logic

---

## 中文说明

### 简介

`step-parser` 是一个纯 Python 的 STEP 文件解析库，专门为**钣金件**的几何特征提取设计。

**零外部依赖** — 仅使用 Python 标准库即可解析 STEP 文件并提取 BREP 几何数据。

### 安装

```bash
pip install step-parser
```

### 三行代码示例

```python
from step_parser import parse, analyze, extract_assembly

store = parse('零件.stp')                          # 解析 STEP 文件
assembly = extract_assembly(store)                 # 提取装配结构
result = analyze(store, assembly['parts'][0])      # 计算几何属性
print(result['name'], result['bbox_mm']['label'])  # → "支架" "120.5×80.3×2.0"
```

### 提取的信息

- 📦 **包围盒** — 长×宽×高 (mm)
- 📐 **表面积** / **展开面积** (m²)
- ✂️ **外轮廓切割长度** (m)
- 🕳️ **孔明细** — 按直径分组，含数量
- 🔩 **攻牙/压铆参考** — 根据孔径推测可能的工艺
- 🔧 **折弯数** — 自动识别折弯特征
- 📏 **板厚** — 从平行平面间距估算
- ⚖️ **净重** — 基于 SPCC 密度估算
- 🏷️ **零件类型** — 平板件 / 折弯件

---

## 📢 完整报价工具

`step-parser` 是 **[smHelper](https://smhelper.gzyrwl.com)** 的核心解析引擎。

**smHelper** 是一款完整的钣金报价桌面工具：
- 🖥️ 拖入 STEP 图纸 → 秒出带 3D 视图的专业报价单 HTML
- 🎨 6 套报价单主题，支持离线使用
- 🆓 20 张免费试用，¥98 永久授权

👉 **[访问官网 →](https://smhelper.gzyrwl.com)**

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

## Links

- 🏠 [smHelper 官网](https://smhelper.gzyrwl.com)
- 📦 [PyPI](https://pypi.org/project/step-parser/)
- 🐛 [Issues](https://github.com/smhelper/step-parser/issues)
