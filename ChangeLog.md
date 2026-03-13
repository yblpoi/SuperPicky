# 📝 SuperPicky v4.2.0 ChangeLog / 更新日志

**📅 Release Date / 发布日期**: 2026-03-14\
**🏷️ Version / 版本号**: 4.2.0\
**📦 Git Commit / Git 提交**: 6c31cf7

***

## 🚀 Major Updates / 重大更新

### 1. 🤖 Brand-new ONNX Runtime Inference Engine / 全新 ONNX Runtime 推理引擎

- **🏗️ Core Architecture Upgrade / 核心架构升级**: Complete replacement of PyTorch inference engine with ONNX Runtime / 完全替换 PyTorch 推理引擎为 ONNX Runtime
- **⚡ Performance Boost / 性能提升**: Faster pure CPU inference, significantly smaller package size / 纯 CPU 推理速度更快，包体积显著减小
- **📦 New Modules / 新增模块**:
  - `ai_model_onnx.py` - Core inference module / 核心推理模块
  - `bird_identifier_onnx.py` - Bird identifier ONNX implementation / 鸟类识别 ONNX 实现
  - `osea_classifier_onnx.py` - OSEA classifier ONNX implementation / OSEA 分类器 ONNX 实现
  - `flight_detector_onnx.py` - Flight detector ONNX implementation / 飞版检测 ONNX 实现
  - `keypoint_detector_onnx.py` - Keypoint detector ONNX implementation / 关键点检测 ONNX 实现
  - `iqa_scorer_onnx.py` - Image quality scorer ONNX implementation / 图像质量评分 ONNX 实现
  - `topiq_model_onnx.py` - TOPIQ aesthetic scorer ONNX implementation / TOPIQ 美学评分 ONNX 实现
- **🔄 Model Conversion / 模型转换**: Added 5 model conversion scripts (`scripts/convert_*.py`) / 新增 5 个模型转换脚本（`scripts/convert_*.py`）
- **🌐 Model Hosting / 模型托管**: Models hosted on HuggingFace, downloaded via `scripts/download_models.py` / 模型通过 HuggingFace 下载，使用 `scripts/download_models.py`
- **📦 Packaging Config / 打包配置**: Added PyInstaller spec files for macOS and Windows ONNX versions / 新增 macOS 和 Windows ONNX 版本的 PyInstaller spec 文件

***

## ✨ New Features & Improvements / 新功能与改进

### 2. 🏗️ Build System Optimization / 构建系统优化

- 📄 Added `requirements_onnx.txt` - Dedicated dependency file for ONNX version / 新增 `requirements_onnx.txt` - ONNX 版本专用依赖文件
- 📦 Added `build_release_win.py` - Windows version build script / 新增 `build_release_win.py` - Windows 版本构建脚本
- 🔄 Updated GitHub Actions workflow for ONNX version auto-build / 更新 GitHub Actions 工作流，支持 ONNX 版本自动构建
- 📝 Updated `scripts/update_inno_version.py` to support simultaneous update of `core/build_info.py` / 更新 `scripts/update_inno_version.py`，支持同时更新 `core/build_info.py`
- 📄 Added `ChangeLog.md` to release assets / 添加 `ChangeLog.md` 到发布资源

### 3. 📦 Dependency Management / 依赖管理

- 📄 Updated `requirements_base.txt`: Added `pi-heif` for HEIF/HEIC format support / `requirements_base.txt` 更新：添加 `pi-heif`，用于 HEIF/HEIC 格式支持
- 🔥 Removed PyTorch-related dependencies (Nightly branch supports ONNX only) / 移除 PyTorch 相关依赖（Nightly 分支仅支持 ONNX）

***

## 🐛 Bug Fixes / Bug 修复

### 4. 🔧 Core Feature Fixes / 核心功能修复

- **🐦 Fixed bird name search database empty issue** (commit 5239abb) / **修复鸟名搜索数据库为空问题** (commit 5239abb)
  - 📂 Resolved `ioc/birdname.db` path issue after packaging / 解决打包后 `ioc/birdname.db` 路径问题
  - 📦 Updated `SuperPicky_onnx.spec` to properly package database file / 更新 `SuperPicky_onnx.spec` 正确打包数据库文件
  - 🔧 Fixed database loading logic in `ui/birdname_search_widget.py` / 修复 `ui/birdname_search_widget.py` 数据库加载逻辑
- **🏷️ Fixed Chinese path garbled issue** (commit 4f3425a) / **修复中文路径乱码问题** (commit 4f3425a)
  - 🔧 Fixed Chinese path encoding issues passed to cv2 and rawpy / 修正输入到 cv2 和 rawpy 的图片路径中文乱码问题
- **🌍 Fixed i18n output encoding issue** (commit 6b3e847) / **修复 i18n 输出编码问题** (commit 6b3e847)
  - 🔧 Fixed non-Unicode encoding output for internationalized text / 修复国际化文本非 Unicode 编码输出问题

### 5. 💻 Platform Compatibility Fixes / 平台兼容性修复

#### 🍎 macOS

- **🔒 Fixed macOS packaged app permission crash** (commit 5239abb) / **修复 macOS 打包应用权限崩溃** (commit 5239abb)
  - 🔧 Resolved permission issues with packaged macOS ONNX app / 解决打包版 macOS ONNX 应用权限问题
- **📂 Fixed macOS GUI startup directory issue** (commit 7e58bea) / **修复 macOS GUI 启动目录问题** (commit 7e58bea)
  - 🏠 Set CWD to user home directory to avoid YOLO runs/ write failure / 设置 CWD 为用户主目录，避免 YOLO runs/ 写入失败
- **📋 Fixed macOS QComboBox unclickable issue** (commit 458073c) / **修复 macOS QComboBox 不可点击问题** (commit 458073c)
  - 🎨 Aligned QComboBox CSS with FilterPanel / 调整 QComboBox CSS 与 FilterPanel 对齐
  - 🔧 Fixed macOS dropdown menu unclickable issue / 修复 macOS 下拉菜单不可点击问题
- **📂 Fixed macOS packaged resource path issue** (commit 9d58ddd) / **修复 macOS 打包资源路径问题** (commit 9d58ddd)
  - 🔧 Resolved correct PyInstaller BUNDLE data path issue / 解决正确的 PyInstaller BUNDLE 数据路径问题
- **📂 Fixed packaged app database path issue** (commit 6e37f8d) / **修复打包应用数据库路径问题** (commit 6e37f8d)
  - 🔧 Use `sys._MEIPASS` in frozen app for `birdname.db` path / 在冻结应用中使用 `sys._MEIPASS` 处理 `birdname.db` 路径
- **📦 Added birdname.db to packaged resources** (commit 68fa1cf) / **添加 birdname.db 到打包资源** (commit 68fa1cf)
  - 📦 Added `ioc/birdname.db` to bundle, fixed bird name query display empty issue / 将 `ioc/birdname.db` 加入 bundle，修复查询鸟名显示为空的问题

#### 🪟 Windows

- **📝 Updated Inno Setup version script** (not listed separately in commit) / **更新 Inno Setup 版本脚本** (commit 中未单独列出)
  - 🔧 Supports simultaneous update of COMMIT\_HASH in `core/build_info.py` / 支持同时更新 `core/build_info.py` 的 COMMIT\_HASH
  - 🔧 Improved OutputBaseFilename matching logic / 改进 OutputBaseFilename 匹配逻辑

### 6. 🔄 Process Management Fixes / 进程管理修复

- **✅ Ensure ExifTool process proper cleanup** (commit c69277f) / **确保 ExifTool 进程正确清理** (commit c69277f)
  - 🔧 Optimized low-level management to ensure complete termination of background resident ExifTool service on app exit / 优化底层管理，确保应用退出时完全终止后台常驻的 ExifTool 服务

### 7. 🧹 Other Fixes / 其他修复

- **🗑️ Removed duplicate root-level birdname.db** (commit 8b1e1f2) / **移除重复的 root-level birdname.db** (commit 8b1e1f2)
  - 📂 `ioc/birdname.db` is the official working copy / `ioc/birdname.db` 为正式使用的副本
- **🔥 Removed PyTorch models from download list** (commit 2477d46) / **移除 PyTorch 模型从下载列表** (commit 2477d46)
  - 📦 Nightly branch is ONNX-only, no longer provides PyTorch models / Nightly 分支为 ONNX-only，不再提供 PyTorch 模型
- **🔧 Fixed ONNX CPU inference message** (commit 6c31cf7) / **修复 ONNX CPU 推理消息** (commit 6c31cf7)
  - 📝 Updated related prompt messages / 更新相关提示信息

***

## ✅ Validation Requirements / 验证要求

According to project rules, this version includes the following validations: / 根据项目规则，本版本包含以下验证：

- ✅ Python syntax check / Python 语法检查
- ✅ Chinese metadata write verification / 中文元数据写入验证
- ✅ SQLite thread-safe handling / SQLite 线程安全处理
- ✅ ExifTool process safe shutdown / ExifTool 进程安全关闭
- ✅ Cross-platform path compatibility / 跨平台路径兼容性

***

## 📋 Upgrade Recommendations / 升级建议

1. **🍎 macOS Users / macOS 用户**: First launch may require permission in "System Settings > Privacy & Security" / 首次打开可能需要在"系统设置 > 隐私与安全性"中允许运行
2. **🪟 Windows Users / Windows 用户**: If blocked by antivirus, please add to trust / 如遇杀毒软件拦截，请添加信任

***

## 🆘 Technical Support / 技术支持

If you encounter any issues, please reach out via: / 如遇问题，请通过以下方式获取帮助：

- 🐙 GitHub Issues: <https://github.com/jamesphotography/SuperPicky/issues>

