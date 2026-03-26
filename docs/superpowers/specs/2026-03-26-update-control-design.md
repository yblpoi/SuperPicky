# Update Control Design

**Date:** 2026-03-26
**Status:** Approved

## Summary

Add two user-controlled settings to the update notification system:

1. **Skip this version** — "跳过此版本" button in the update dialog; suppresses the startup reminder for that specific version until a newer version is released.
2. **Include pre-release** — Checkbox in the update dialog (and persisted in config) to opt into Beta/RC update notifications.

---

## Config Changes (`advanced_config.py`)

Two new fields in `DEFAULT_CONFIG`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ignored_update_version` | `str \| None` | `None` | Version string to suppress, e.g. `"4.3.0"`. Cleared automatically when a newer version is released. |
| `include_prerelease` | `bool` | `False` | Whether to include Beta/RC releases in update checks. |

New getters/setters follow existing patterns:
- `ignored_update_version` property + `set_ignored_update_version(value: str | None)`
- `include_prerelease` property + `set_include_prerelease(value: bool)`

---

## UpdateChecker Changes (`tools/update_checker.py`)

`check_for_updates(timeout, include_prerelease)` gains a new parameter:

- **`include_prerelease=False`** (default): unchanged — calls `/releases/latest`, returns stable releases only.
- **`include_prerelease=True`**: calls `/repos/{repo}/releases` (list endpoint), iterates releases sorted by `published_at` descending, picks the first one (stable or pre-release), compares against current version.

The `GITHUB_API_URL` constant stays as-is; a new `GITHUB_RELEASES_LIST_URL` constant is added for the list endpoint.

---

## Main Window Changes (`ui/main_window.py`)

### `_check_for_updates`

1. Read `include_prerelease` from `advanced_config` and pass to `UpdateChecker.check_for_updates()`.
2. After getting `has_update=True` and `latest_version`:
   - If `silent=True` and `latest_version == cfg.ignored_update_version` → skip dialog silently.
   - Otherwise proceed as before.

### `_show_update_result_dialog`

Changes apply only when `has_update=True`:

**"跳过此版本" button:**
- Positioned next to the existing "关闭" button.
- On click: calls `cfg.set_ignored_update_version(latest_version)` + `cfg.save()`, then closes dialog.
- Styled as a secondary/muted button (same style as "关闭").

**`include_prerelease` checkbox:**
- Positioned below the download buttons, above the close row.
- Label: `"接收预发布版本提醒（Beta / RC）"` (zh) / `"Notify me about pre-release versions (Beta / RC)"` (en).
- Initialised from `cfg.include_prerelease`.
- On toggle: calls `cfg.set_include_prerelease(checked)` + `cfg.save()` immediately (no need to re-check; takes effect next startup or next manual check).

---

## Data Flow

```
Startup (silent=True)
  │
  ├─ read include_prerelease from config
  ├─ UpdateChecker.check_for_updates(include_prerelease=...)
  │     ├─ False → GET /releases/latest
  │     └─ True  → GET /releases (list), pick latest
  │
  ├─ has_update=False → silent, do nothing
  └─ has_update=True
        ├─ latest_version == ignored_update_version → silent, do nothing
        └─ show dialog
              ├─ [跳过此版本] → save ignored_update_version, close
              ├─ [include_prerelease checkbox] → save include_prerelease
              └─ [关闭] → close
```

---

## Edge Cases

| Case | Behaviour |
|------|-----------|
| User skips v4.3.0; v4.3.1 is released | `ignored_update_version="4.3.0"` ≠ `"4.3.1"` → dialog shows again |
| User enables prerelease; latest is a pre-release older than current | `has_update=False` → no dialog |
| Manual menu check with skipped version | Skip logic only applies in `silent=True` mode; manual check always shows dialog |
| `include_prerelease` toggled in dialog | Takes effect on next check (startup or manual), not immediately |

---

## Files to Change

| File | Change |
|------|--------|
| `advanced_config.py` | Add 2 config fields + getter/setter pairs |
| `tools/update_checker.py` | Add `include_prerelease` param + list-endpoint logic |
| `ui/main_window.py` | Update `_check_for_updates` + `_show_update_result_dialog` |
| `locales/zh_CN.json` | Add i18n keys for new UI strings |
| `locales/en_US.json` | Add i18n keys for new UI strings |
