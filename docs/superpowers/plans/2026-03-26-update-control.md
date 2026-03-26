# Update Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "跳过此版本" button and `include_prerelease` checkbox to the update dialog, backed by two new `advanced_config` fields.

**Architecture:** Config layer (`advanced_config.py`) stores user preferences → `UpdateChecker` reads `include_prerelease` to switch between stable-only and all-releases API endpoints → `main_window.py` reads `ignored_update_version` to suppress dialogs and renders the new dialog controls.

**Tech Stack:** Python 3, PySide6, GitHub REST API v3, `packaging.version`

---

## Files

| File | Change |
|------|--------|
| `advanced_config.py` | Add `ignored_update_version` + `include_prerelease` fields, getters, setters |
| `tools/update_checker.py` | Add `include_prerelease` param; add list-endpoint path |
| `ui/main_window.py` | Skip ignored version in `_check_for_updates`; add button + checkbox in `_show_update_result_dialog` |
| `locales/zh_CN.json` | Add `update.include_prerelease` key |
| `locales/en_US.json` | Add `update.include_prerelease` key |

---

### Task 1: Add config fields to `advanced_config.py`

**Files:**
- Modify: `advanced_config.py`

- [ ] **Step 1: Add two fields to `DEFAULT_CONFIG`**

In `advanced_config.py`, inside `DEFAULT_CONFIG` after the `"delete_confirm"` entry add:

```python
        # 更新提醒控制
        "ignored_update_version": None,  # 跳过提醒的版本号，如 "4.3.0"
        "include_prerelease": False,      # 是否接收 Beta/RC 更新提醒
```

- [ ] **Step 2: Add getters**

After the `delete_confirm` property (around line 354) add:

```python
    @property
    def ignored_update_version(self):
        return self.config.get("ignored_update_version", None)

    @property
    def include_prerelease(self) -> bool:
        return self.config.get("include_prerelease", False)
```

- [ ] **Step 3: Add setters**

After the `set_delete_confirm` method add:

```python
    def set_ignored_update_version(self, value):
        """设置要跳过提醒的版本号，传 None 清除。"""
        self.config["ignored_update_version"] = value if isinstance(value, str) else None

    def set_include_prerelease(self, value: bool):
        """设置是否接收预发布版本提醒。"""
        self.config["include_prerelease"] = bool(value)
```

- [ ] **Step 4: Verify syntax**

```bash
python3 -m py_compile advanced_config.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add advanced_config.py
git commit -m "feat: add ignored_update_version and include_prerelease config fields"
```

---

### Task 2: Add i18n keys for `include_prerelease` checkbox

**Files:**
- Modify: `locales/zh_CN.json`
- Modify: `locales/en_US.json`

- [ ] **Step 1: Add key to `zh_CN.json`**

In `locales/zh_CN.json`, inside the `"update"` object, after `"close"` add:

```json
    "include_prerelease": "接收预发布版本提醒（Beta / RC）"
```

- [ ] **Step 2: Add key to `en_US.json`**

In `locales/en_US.json`, inside the `"update"` object, after `"close"` add:

```json
    "include_prerelease": "Notify me about pre-release versions (Beta / RC)"
```

- [ ] **Step 3: Verify JSON syntax**

```bash
python3 -c "import json; json.load(open('locales/zh_CN.json')); json.load(open('locales/en_US.json')); print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add locales/zh_CN.json locales/en_US.json
git commit -m "feat: add i18n key for include_prerelease checkbox"
```

---

### Task 3: Update `UpdateChecker` to support pre-release versions

**Files:**
- Modify: `tools/update_checker.py`

- [ ] **Step 1: Add the list-endpoint constant**

After `GITHUB_API_URL` (line 23) add:

```python
GITHUB_RELEASES_LIST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
```

- [ ] **Step 2: Add `include_prerelease` parameter to `check_for_updates`**

Change the method signature from:

```python
    def check_for_updates(self, timeout: int = 10) -> Tuple[bool, Optional[Dict]]:
```

to:

```python
    def check_for_updates(self, timeout: int = 10, include_prerelease: bool = False) -> Tuple[bool, Optional[Dict]]:
```

- [ ] **Step 3: Add list-endpoint branch**

Replace the current request block (lines ~75-84, the `req = urllib.request.Request(...)` + `urlopen` call) with:

```python
            # 选择 API 端点
            api_url = GITHUB_RELEASES_LIST_URL if include_prerelease else GITHUB_API_URL

            req = urllib.request.Request(
                api_url,
                headers={
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': f'SuperPicky/{self.current_version}'
                }
            )

            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
                raw = json.loads(response.read().decode('utf-8'))

            # /releases 返回列表，/releases/latest 返回单个对象
            if include_prerelease:
                # 取发布时间最新的一条（列表已按 published_at 倒序）
                data = raw[0] if raw else {}
            else:
                data = raw
```

- [ ] **Step 4: Verify syntax**

```bash
python3 -m py_compile tools/update_checker.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add tools/update_checker.py
git commit -m "feat: support include_prerelease in UpdateChecker"
```

---

### Task 4: Update `_check_for_updates` in `main_window.py`

**Files:**
- Modify: `ui/main_window.py`

- [ ] **Step 1: Read config and pass `include_prerelease` to checker**

In `_check_for_updates`, inside `_do_check()`, replace:

```python
                checker = UpdateChecker()  # 使用 update_checker.CURRENT_VERSION
                has_update, update_info = checker.check_for_updates()
```

with:

```python
                from advanced_config import get_advanced_config as _get_cfg
                _cfg = _get_cfg()
                checker = UpdateChecker()
                has_update, update_info = checker.check_for_updates(
                    include_prerelease=_cfg.include_prerelease
                )
```

- [ ] **Step 2: Skip ignored version in silent mode**

After the existing `if silent and not has_update:` block (around line 2701), add a new check immediately after:

```python
                # 静默模式：跳过用户已选择忽略的版本
                if silent and has_update and update_info:
                    latest = update_info.get('version', '')
                    if latest and latest == _cfg.ignored_update_version:
                        print(f"[DEBUG] Silent mode, version {latest} is ignored, skipping dialog")
                        return
```

- [ ] **Step 3: Verify syntax**

```bash
python3 -m py_compile ui/main_window.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add ui/main_window.py
git commit -m "feat: skip ignored version and pass include_prerelease in update check"
```

---

### Task 5: Add "跳过此版本" button and `include_prerelease` checkbox to dialog

**Files:**
- Modify: `ui/main_window.py`

This task modifies `_show_update_result_dialog`. Both controls only appear when `has_update=True`.

- [ ] **Step 1: Add "跳过此版本" button next to "关闭"**

Find the close button section (around line 2854–2876):

```python
            # 关闭按钮
            close_layout = QHBoxLayout()
            close_layout.addStretch()

            close_btn = QPushButton(self.i18n.t("update.close"))
            ...
            close_btn.clicked.connect(dialog.accept)
            close_layout.addWidget(close_btn)

            layout.addLayout(close_layout)
```

Replace with:

```python
            # 关闭 / 跳过此版本 按钮行
            close_layout = QHBoxLayout()
            close_layout.addStretch()

            if has_update and update_info:
                skip_btn = QPushButton(self.i18n.t("update.skip_version"))
                skip_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {COLORS['bg_card']};
                        border: 1px solid {COLORS['border']};
                        color: {COLORS['text_muted']};
                        border-radius: 6px;
                        padding: 8px 16px;
                        font-size: 13px;
                    }}
                    QPushButton:hover {{
                        border-color: {COLORS['text_muted']};
                        color: {COLORS['text_secondary']};
                    }}
                """)
                def _on_skip():
                    from advanced_config import get_advanced_config as _get_cfg
                    _cfg = _get_cfg()
                    _cfg.set_ignored_update_version(update_info.get('version', ''))
                    _cfg.save()
                    dialog.accept()
                skip_btn.clicked.connect(_on_skip)
                close_layout.addWidget(skip_btn)
                close_layout.addSpacing(8)

            close_btn = QPushButton(self.i18n.t("update.close"))
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_card']};
                    border: 1px solid {COLORS['border']};
                    color: {COLORS['text_secondary']};
                    border-radius: 6px;
                    padding: 8px 24px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    border-color: {COLORS['text_muted']};
                    color: {COLORS['text_primary']};
                }}
            """)
            close_btn.clicked.connect(dialog.accept)
            close_layout.addWidget(close_btn)

            layout.addLayout(close_layout)
```

- [ ] **Step 2: Add `include_prerelease` checkbox above button row**

Before the `# 关闭 / 跳过此版本 按钮行` block added above, insert:

```python
            if has_update:
                from PySide6.QtWidgets import QCheckBox
                from advanced_config import get_advanced_config as _get_cfg
                _cfg = _get_cfg()
                prerelease_cb = QCheckBox(self.i18n.t("update.include_prerelease"))
                prerelease_cb.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
                prerelease_cb.setChecked(_cfg.include_prerelease)
                def _on_prerelease_toggled(checked):
                    _c = _get_cfg()
                    _c.set_include_prerelease(checked)
                    _c.save()
                prerelease_cb.toggled.connect(_on_prerelease_toggled)
                layout.addWidget(prerelease_cb)
                layout.addSpacing(4)
```

- [ ] **Step 3: Verify syntax**

```bash
python3 -m py_compile ui/main_window.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 4: Remove debug print statements**

Remove these two lines added during earlier debugging:

```python
print("[DEBUG] 即将显示弹窗")
print("[DEBUG] 弹窗已关闭")
```

Also remove the `[DEBUG] Update check done` and `[DEBUG] Silent mode` prints in `_check_for_updates` if desired.

- [ ] **Step 5: Verify syntax again**

```bash
python3 -m py_compile ui/main_window.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add ui/main_window.py
git commit -m "feat: add skip-version button and include-prerelease checkbox to update dialog"
```

---

## Manual Test Checklist

After all tasks are done, run `python3 main.py` and verify:

1. **Skip version works:**
   - Trigger update dialog (temporarily set `APP_VERSION` to an older version like `"3.0.0"` in `constants.py`)
   - Click "跳过此版本"
   - Restart app → no update dialog appears
   - Restore `APP_VERSION`

2. **include_prerelease checkbox:**
   - Open update dialog → checkbox shows current state from config
   - Toggle checkbox → restart app → check `advanced_config.json` has updated value

3. **Manual check ignores skip:**
   - Set `ignored_update_version` to latest version in config
   - Use menu "检查更新" → dialog still appears (skip only applies to silent mode)
