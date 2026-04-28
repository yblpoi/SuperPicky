# SuperPicky 依赖版本核对记录

日期：2026-04-11

## 目的

记录 SuperPicky 当前依赖版本状态，作为后续排查兼容性问题和计划升级时的参考。

本次仅做核对与整理，没有修改项目代码或依赖文件。

## 核对范围

- 仓库声明依赖：
  - `requirements.txt`
  - `requirements_base.txt`
  - `requirements_mac.txt`
  - `requirements_cuda.txt`
- 本地虚拟环境：
  - `.venv`

本次检查时，本地 `.venv` Python 版本为 `3.12.8`。

## 当前项目依赖说明

项目依赖分两类：

1. 仓库声明版本
   - 部分依赖是固定版本，例如 macOS 的 `torch==2.8.0`
   - 也有很多依赖只是下限版本，例如 `numpy>=1.20.0`

2. 本地实际安装版本
   - 以 `.venv` 中 `pip list --format=freeze` 为准

注意：

- 由于很多依赖只写了 `>=`，所以“仓库允许安装的版本”和“当前机器实际安装的版本”不一定相同。
- 当前 TOPIQ 实际运行使用的是仓库内置实现 `topiq_model.py`，不是 `pyiqa` 包本身。

## 当前已确认的本地实际版本

### 重点依赖

- `torch==2.8.0`
- `torchvision==0.23.0`
- `ultralytics==8.3.199`
- `timm==1.0.20`
- `numpy==2.2.6`
- `Pillow==11.3.0`
- `PySide6==6.10.1`
- `cryptography==46.0.3`
- `huggingface-hub==0.35.3`
- `pyinstaller==6.16.0`
- `opencv-python==4.13.0.92`
- `rawpy==0.26.1`
- `pillow-heif==1.3.0`
- `Flask==3.1.2`
- `flask-cors==6.0.2`
- `ImageHash==4.3.2`
- `imageio==2.37.0`
- `tzdata==2025.2`
- `pyiqa==0.1.15.post2`

## 可升级项与变化摘要

以下是当时检查到的“存在升级空间”的主要依赖。

### 1. PyTorch

- 当前：`2.8.0`
- 官方最新稳定：`2.11.0`

主要变化：

- Apple Silicon / MPS 算子覆盖继续扩展
- 中间跨越 `2.9.0`、`2.10.0`、`2.11.0` 三个稳定版本
- 对 macOS / MPS 路径更值得关注

对项目的意义：

- 如果后续重新评估 `M5 + MPS + TOPIQ` 问题，PyTorch 是最值得优先尝试的升级项

### 2. Ultralytics

- 当前：`8.3.199`
- 检查时最新：`8.4.37`

主要变化：

- 上游持续演进检测、分割、姿态和导出路径
- 已经进入 `YOLO26` 代际语境

风险点：

- 项目依赖 YOLO 结果结构
- 升级后需要回归 `bbox / mask / keypoint` 输出

### 3. Pillow

- 当前：`11.3.0`
- 检查时最新：`12.2.0`

主要变化：

- `12.0.0` 有一批不兼容移除
- `12.2.0` 包含多项修复与性能改进

风险点：

- 升级到 `12.x` 需要确认项目中使用的 API 没有踩到移除项

### 4. PySide6

- 当前：`6.10.1`
- 检查时最新：`6.11.0`

主要变化：

- Qt for Python 已进入 `6.11` 线
- 中间还有多个修补版本

风险点：

- 项目 UI 面积大
- 升级收益可能有，但 GUI 回归成本高

### 5. timm

- 当前：`1.0.20`
- 检查时最新：`1.0.25`

主要变化：

- 持续补充模型和推理相关改进
- 包括部分精度支持与集成层面的修复

对项目的意义：

- 项目主要使用 `resnet50 features_only=True`
- 相对属于较低风险升级项

### 6. huggingface-hub

- 当前：`0.35.3`
- 检查时最新：`1.6.0`

主要变化：

- 进入 `1.x`
- Hub 和 CLI 能力继续扩展

风险点：

- 项目当前主要只在脚本中使用 `hf_hub_download`、`HfApi`、`whoami`
- 收益不大，但有 API 兼容风险

### 7. PyInstaller

- 当前：`6.16.0`
- 检查时最新：`6.19.0`

主要变化：

- 持续补平台支持和 hook

风险点：

- 项目有自定义 `.spec`
- 升级后需要完整打包 smoke test

### 8. NumPy

- 当前：`2.2.6`
- 检查时最新：`2.4.4`

主要变化：

- 仍在 `2.x` 系列内继续前进

风险点：

- 需要一起验证 `opencv / rawpy / onnxruntime` 这类二进制扩展兼容

### 9. imageio

- 当前：`2.37.0`
- 检查时最新：`2.37.3`

主要变化：

- 小版本修补

结论：

- 升级价值一般

### 10. cryptography

- 当前：`46.0.3`
- 检查时最新：`46.0.7`

主要变化：

- 同大版本内的 patch 更新
- 偏安全和兼容性修复

### 11. tzdata

- 当前：`2025.2`
- 检查时最新：`2025.3`

主要变化：

- 时区数据库更新

## 已经是最新或基本接近最新的依赖

- `opencv-python==4.13.0.92`
- `rawpy==0.26.1`
- `pillow-heif==1.3.0`
- `Flask==3.1.2`
- `flask-cors==6.0.2`
- `ImageHash==4.3.2`

## 风险判断

如果未来要升级，按回归风险大致可分为：

### 高风险

- `torch`
- `ultralytics`
- `PySide6`
- `pyinstaller`

原因：

- 会直接影响推理、UI 或打包链路

### 中风险

- `Pillow`
- `numpy`
- `huggingface-hub`

原因：

- API 或二进制兼容性可能带来间接问题

### 相对低风险

- `timm`
- `imageio`
- `cryptography`
- `tzdata`

## 当时的实际建议

当时给出的建议顺序是：

1. 若要排查 `M5 + MPS`，优先试 `torch`
2. 若只想低风险补强，可先看 `timm`
3. `ultralytics` 和 `PySide6` 放后面，因为回归面最大
4. `Pillow` 可以升，但要先核对 `12.x` 的不兼容项

## 当前决策备注

当前决定：

- 暂不升级依赖
- 保留本记录作为后续备用文档

## 参考来源

- PyTorch Releases
  - https://github.com/pytorch/pytorch/releases
- Ultralytics PyPI
  - https://pypi.org/project/ultralytics/
- Pillow PyPI
  - https://pypi.org/project/Pillow/
- Pillow Release Notes
  - https://pillow.readthedocs.io/en/stable/releasenotes/12.0.0.html
  - https://pillow.readthedocs.io/en/stable/releasenotes/12.2.0.html
- PySide6 PyPI
  - https://pypi.org/project/PySide6/
- timm PyPI
  - https://pypi.org/project/timm/
- huggingface-hub PyPI
  - https://pypi.org/project/huggingface-hub/
- huggingface_hub Releases
  - https://github.com/huggingface/huggingface_hub/releases
- PyInstaller PyPI
  - https://pypi.org/project/pyinstaller/
- NumPy PyPI
  - https://pypi.org/project/numpy/
- cryptography PyPI
  - https://pypi.org/project/cryptography/
- opencv-python PyPI
  - https://pypi.org/project/opencv-python/
- rawpy PyPI
  - https://pypi.org/project/rawpy/
- pillow-heif PyPI
  - https://pypi.org/project/pillow-heif/
- pi-heif PyPI
  - https://pypi.org/project/pi-heif/
- Flask PyPI
  - https://pypi.org/project/Flask/
- flask-cors PyPI
  - https://pypi.org/project/flask-cors/
- ImageHash PyPI
  - https://pypi.org/project/ImageHash/
- tzdata PyPI
  - https://pypi.org/project/tzdata/
