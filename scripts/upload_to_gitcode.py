#!/usr/bin/env python3
"""Upload local release assets to GitCode releases.

中：这个脚本会先确保 GitCode 上存在目标 Release，然后把本地发行文件逐个上传上去。
英：This script first ensures the target GitCode release exists, then uploads local
release files one by one.

中：文件来源优先级如下：
1. 如果设置了 GITCODE_FILES，就按这个环境变量提供的文件列表上传。
2. 如果没有设置 GITCODE_FILES，就默认扫描 release_assets/ 目录下的文件。

英：File source priority:
1. If GITCODE_FILES is set, upload the files listed in that environment variable.
2. Otherwise, scan files from the default release_assets/ directory.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import requests
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


API_BASE = "https://api.gitcode.com/api/v5"
DEFAULT_TIMEOUT: int | None = None
DEFAULT_UPLOAD_ATTEMPTS = 5
DEFAULT_ASSET_DIR = Path("release_assets")
DEFAULT_CHANGELOG_PATH = Path("ChangeLog.md")


class GitCodeError(RuntimeError):
    """Raised when a GitCode API call fails.

    中：统一使用这个异常封装业务错误和接口错误，方便 main() 中集中处理。
    英：All business and API failures are wrapped with this exception so main()
    can handle them in one place.
    """


@dataclass
class Config:
    """Runtime configuration resolved from the environment.

    中：脚本运行时需要的核心参数都会被收敛到这个数据结构中，避免到处直接读取环境变量。
    英：All runtime settings are normalized into this structure so the rest of the
    script does not read environment variables repeatedly.
    """

    token: str
    repo_url: str
    owner: str
    repo: str
    tag: str
    target_branch: str
    skip_release_ensure: bool
    timeout_seconds: int | None
    upload_attempts: int
    release_name: str
    release_body: str
    files: list[Path]


@dataclass
class UploadTarget:
    """Upload endpoint information returned by GitCode.

    中：GitCode 文档里没有完整公开 upload_url 的返回结构，所以这里做了一个宽松的数据模型，
    兼容常见的上传方式，例如直接 PUT 二进制，或者 POST multipart/form-data。
    英：GitCode does not fully document the upload_url response shape, so this model
    stays intentionally flexible and supports common patterns such as raw PUT uploads
    and multipart/form-data POST uploads.
    """

    url: str
    method: str = "PUT"
    headers: dict[str, str] | None = None
    form_fields: dict[str, str] | None = None
    file_field_name: str = "file"
    filename_query_key: str | None = "file_name"


class ProgressReporter:
    """Render a single-line upload progress bar.

    中：这个类负责把“已发送大小 / 总大小、实时速度、预计剩余时间”渲染到同一行，
    方便观察大文件上传进度而不刷屏。
    英：This class renders sent bytes, total bytes, speed, and ETA on one line so
    large uploads can be observed without flooding the terminal.
    """

    def __init__(self, label: str, total_bytes: int) -> None:
        self.label = label
        self.total_bytes = max(total_bytes, 1)
        self.sent_bytes = 0
        self.start_time = time.time()
        self.last_render_at = 0.0

    def update(self, chunk_size: int) -> None:
        self.sent_bytes += chunk_size
        now = time.time()
        if self.sent_bytes >= self.total_bytes or now - self.last_render_at >= 0.2:
            self.last_render_at = now
            self.render()

    def finish(self) -> None:
        self.sent_bytes = self.total_bytes
        self.render()
        print()

    def render(self) -> None:
        elapsed = max(time.time() - self.start_time, 0.001)
        speed = self.sent_bytes / elapsed
        remaining_bytes = max(self.total_bytes - self.sent_bytes, 0)
        eta_seconds = remaining_bytes / speed if speed > 0 else 0
        percent = min(self.sent_bytes / self.total_bytes, 1.0)
        filled = int(percent * 24)
        bar = "#" * filled + "-" * (24 - filled)
        message = (
            f"\r[{bar}] {percent * 100:6.2f}% "
            f"{format_bytes(self.sent_bytes)}/{format_bytes(self.total_bytes)} "
            f"{format_bytes(speed)}/s ETA {format_duration(eta_seconds)} "
            f"{self.label}"
        )
        print(message, end="", flush=True)


class RawUploadStream:
    """Stream a file in chunks while reporting progress.

    中：用于直接 PUT/POST 文件二进制内容的场景，避免把大文件整个读入内存。
    英：Used for direct binary uploads so large files do not need to be loaded into
    memory all at once.
    """

    def __init__(self, artifact: Path, reporter: ProgressReporter, chunk_size: int = 1024 * 1024) -> None:
        self.artifact = artifact
        self.reporter = reporter
        self.chunk_size = chunk_size
        self.total_bytes = artifact.stat().st_size

    def __len__(self) -> int:
        return self.total_bytes

    def __iter__(self):
        with self.artifact.open("rb") as handle:
            while True:
                chunk = handle.read(self.chunk_size)
                if not chunk:
                    break
                self.reporter.update(len(chunk))
                yield chunk


class MultipartUploadStream:
    """Stream a multipart/form-data body while reporting progress.

    中：当服务端要求 multipart 时，我们把前导字段、文件内容和结尾边界分块发送，
    同时统计真实发送的总字节数。
    英：When the server requires multipart uploads, this stream sends preamble
    fields, file bytes, and the closing boundary in chunks while tracking the true
    transmitted byte count.
    """

    def __init__(
        self,
        *,
        fields: dict[str, str],
        file_field_name: str,
        artifact: Path,
        content_type: str,
        reporter: ProgressReporter,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        self.artifact = artifact
        self.reporter = reporter
        self.chunk_size = chunk_size
        self.boundary = f"----Release2GitCode{uuid.uuid4().hex}"
        self.content_type_header = f"multipart/form-data; boundary={self.boundary}"
        self.prefix_chunks = self._build_prefix(fields, file_field_name, artifact.name, content_type)
        self.suffix_chunk = f"\r\n--{self.boundary}--\r\n".encode("utf-8")
        self.total_bytes = (
            sum(len(chunk) for chunk in self.prefix_chunks)
            + artifact.stat().st_size
            + len(self.suffix_chunk)
        )

    def __len__(self) -> int:
        return self.total_bytes

    def _build_prefix(
        self,
        fields: dict[str, str],
        file_field_name: str,
        filename: str,
        content_type: str,
    ) -> list[bytes]:
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.append(
                (
                    f"--{self.boundary}\r\n"
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        chunks.append(
            (
                f"--{self.boundary}\r\n"
                f'Content-Disposition: form-data; name="{file_field_name}"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        return chunks

    def __iter__(self):
        for chunk in self.prefix_chunks:
            self.reporter.update(len(chunk))
            yield chunk

        with self.artifact.open("rb") as handle:
            while True:
                chunk = handle.read(self.chunk_size)
                if not chunk:
                    break
                self.reporter.update(len(chunk))
                yield chunk

        self.reporter.update(len(self.suffix_chunk))
        yield self.suffix_chunk


def eprint(message: str) -> None:
    """Print a message to stderr.

    中：错误和诊断信息统一输出到标准错误，方便在 CI 日志中区分普通输出和失败信息。
    英：Send errors and diagnostics to stderr so CI logs can distinguish them from
    normal progress output.
    """

    print(message, file=sys.stderr)


def load_config() -> Config:
    """Load configuration from environment variables.

    中：这里负责三件事：
    1. 校验必填环境变量；
    2. 解析待上传文件来源；
    3. 为可选字段填充默认值。

    英：This function does three things:
    1. validate required environment variables;
    2. resolve the artifact source;
    3. apply defaults for optional fields.
    """

    required_keys = ["GITCODE_TOKEN"]
    missing = [key for key in required_keys if not os.getenv(key, "").strip()]
    if missing:
        raise GitCodeError(f"Missing required environment variables: {', '.join(missing)}")

    files_env = os.getenv("GITCODE_FILES", "")
    files = parse_files_env(files_env) if files_env.strip() else discover_default_assets()
    validate_files(files)

    release_body = resolve_release_body()
    repo_url, owner, repo = resolve_repository()
    tag = resolve_tag(release_body)
    target_branch = os.getenv("GITCODE_TARGET_BRANCH", "").strip() or resolve_target_branch(owner, repo)
    skip_release_ensure = os.getenv("GITCODE_SKIP_RELEASE_ENSURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    timeout_seconds = parse_timeout_seconds(os.getenv("GITCODE_TIMEOUT", ""))
    upload_attempts = parse_upload_attempts(os.getenv("GITCODE_UPLOAD_ATTEMPTS", ""))
    release_name = os.getenv("GITCODE_RELEASE_NAME", "").strip() or tag

    return Config(
        token=os.environ["GITCODE_TOKEN"].strip(),
        repo_url=repo_url,
        owner=owner,
        repo=repo,
        tag=tag,
        target_branch=target_branch,
        skip_release_ensure=skip_release_ensure,
        timeout_seconds=timeout_seconds,
        upload_attempts=upload_attempts,
        release_name=release_name,
        release_body=release_body,
        files=files,
    )


def resolve_repository() -> tuple[str, str, str]:
    """Resolve repo_url, owner, and repo from environment input.

    中：现在默认只要求提供仓库链接；如果还保留旧的 OWNER/REPO 方式，也继续兼容。
    英：The new default only requires a repository URL, but the legacy OWNER/REPO
    environment variables are still accepted for backward compatibility.
    """

    repo_url = os.getenv("GITCODE_REPO_URL", "").strip()
    if repo_url:
        return parse_repo_url(repo_url)

    owner = os.getenv("GITCODE_OWNER", "").strip()
    repo = os.getenv("GITCODE_REPO", "").strip()
    if owner and repo:
        return f"https://gitcode.com/{owner}/{repo}", owner, repo

    raise GitCodeError(
        "Missing repository location. Set GITCODE_REPO_URL or the legacy "
        "GITCODE_OWNER/GITCODE_REPO pair."
    )


def parse_repo_url(repo_url: str) -> tuple[str, str, str]:
    """Parse a GitCode repository URL into owner and repo.

    中：支持 `https://gitcode.com/owner/repo` 和带 `.git` 后缀的形式。
    英：Supports `https://gitcode.com/owner/repo` and the same URL with a `.git`
    suffix.
    """

    parsed = parse.urlparse(repo_url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "gitcode.com":
        raise GitCodeError(f"Unsupported GitCode repository URL: {repo_url}")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise GitCodeError(f"Repository URL is missing owner or repo: {repo_url}")

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        raise GitCodeError(f"Repository URL is missing owner or repo: {repo_url}")

    normalized = f"https://gitcode.com/{owner}/{repo}"
    return normalized, owner, repo


def resolve_release_body() -> str:
    """Resolve release notes from env or ChangeLog.md.

    中：优先使用显式传入的 GITCODE_RELEASE_BODY；未提供时自动读取根目录 ChangeLog.md。
    英：Prefer an explicit GITCODE_RELEASE_BODY override; otherwise load ChangeLog.md
    from the repository root automatically.
    """

    body = os.getenv("GITCODE_RELEASE_BODY")
    if body is not None and body.strip():
        return body

    if DEFAULT_CHANGELOG_PATH.is_file():
        return DEFAULT_CHANGELOG_PATH.read_text(encoding="utf-8")

    return ""


def resolve_tag(release_body: str) -> str:
    """Resolve tag from env or release notes content.

    中：优先级如下：
    1. GITCODE_TAG
    2. GitHub Actions 提供的 tag 参数
    3. ChangeLog 标题中的版本号

    英：Resolution order:
    1. GITCODE_TAG
    2. tag metadata provided by GitHub Actions
    3. version extracted from the changelog heading
    """

    env_tag = os.getenv("GITCODE_TAG", "").strip()
    if env_tag:
        return env_tag

    github_actions_tag = resolve_github_actions_tag()
    if github_actions_tag:
        return github_actions_tag

    if release_body:
        first_line = next((line.strip() for line in release_body.splitlines() if line.strip()), "")
        patterns = [
            r"/\s*(v[0-9A-Za-z.\-_]+)\s*$",
            r"\b(v\d+(?:\.\d+)+(?:[-._][0-9A-Za-z]+)*)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, first_line)
            if match:
                return match.group(1)

    raise GitCodeError(
        "Unable to determine release tag. Set GITCODE_TAG, run under GitHub Actions "
        "with tag context, or provide a ChangeLog.md heading that contains the version tag."
    )


def resolve_github_actions_tag() -> str:
    """Resolve tag metadata from GitHub Actions runtime context.

    中：优先读取 `GITHUB_REF_TYPE=tag` + `GITHUB_REF_NAME`，其次尝试解析
    `GITHUB_EVENT_PATH` 中的 `release.tag_name` 或 `ref`。
    英：Prefer `GITHUB_REF_TYPE=tag` + `GITHUB_REF_NAME`, then fall back to
    parsing `release.tag_name` or `ref` from `GITHUB_EVENT_PATH`.
    """

    github_ref_type = os.getenv("GITHUB_REF_TYPE", "").strip()
    github_ref_name = os.getenv("GITHUB_REF_NAME", "").strip()
    if github_ref_type == "tag" and github_ref_name:
        return github_ref_name

    event_path = os.getenv("GITHUB_EVENT_PATH", "").strip()
    if not event_path:
        return ""

    event_file = Path(event_path)
    if not event_file.is_file():
        return ""

    try:
        event_payload = json.loads(event_file.read_text(encoding="utf-8"))
    except Exception:
        return ""

    release = event_payload.get("release")
    if isinstance(release, dict):
        tag_name = str(release.get("tag_name") or "").strip()
        if tag_name:
            return tag_name

    ref = str(event_payload.get("ref") or "").strip()
    prefix = "refs/tags/"
    if ref.startswith(prefix):
        return ref[len(prefix):]

    return ""


def resolve_target_branch(owner: str, repo: str) -> str:
    """Resolve the target branch from env, repo metadata, or local git.

    中：为了进一步简化输入，默认优先读取远端仓库的 default_branch；读不到时再回退到本地当前分支。
    英：To keep configuration minimal, the script first tries the remote repo's
    default branch, then falls back to the current local git branch.
    """

    repo_api_url = f"{API_BASE}/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}"
    token = os.environ["GITCODE_TOKEN"].strip()
    try:
        response = http_json(
            repo_api_url,
            token=token,
            timeout=DEFAULT_TIMEOUT,
            operation="Get repository metadata",
        )
        if isinstance(response, dict):
            default_branch = str(response.get("default_branch") or "").strip()
            if default_branch:
                return default_branch
    except GitCodeError:
        pass

    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            text=True,
            encoding="utf-8",
        ).strip()
        if branch:
            return branch
    except Exception:
        pass

    return ""


def parse_files_env(value: str) -> list[Path]:
    """Parse a newline-separated file list from GITCODE_FILES.

    中：GitHub Actions 里多行环境变量很常见，所以这里按“每行一个文件路径”来解析。
    空行会被自动忽略。
    英：Multi-line environment variables are common in GitHub Actions, so each line
    is treated as one file path. Blank lines are ignored automatically.
    """

    return [Path(line.strip()) for line in value.splitlines() if line.strip()]


def parse_timeout_seconds(value: str) -> int | None:
    """Parse the optional timeout override from the environment.

    中：默认不设置超时，让大文件自己跑完；如果显式设置 GITCODE_TIMEOUT，
    则按秒数覆盖。
    英：By default the script does not enforce a timeout so large uploads can run
    to completion. If GITCODE_TIMEOUT is set, it overrides the behavior in seconds.
    """

    if not value.strip():
        return DEFAULT_TIMEOUT

    try:
        timeout = int(value)
    except ValueError as exc:
        raise GitCodeError("GITCODE_TIMEOUT must be an integer number of seconds") from exc

    if timeout <= 0:
        raise GitCodeError("GITCODE_TIMEOUT must be greater than 0")
    return timeout


def parse_upload_attempts(value: str) -> int:
    """Parse the upload retry count from the environment.

    中：默认重试 5 次，主要覆盖连接被重置、网络抖动和短暂 5xx。
    英：Uploads retry 5 times by default to handle connection resets, transient
    network issues, and temporary 5xx responses.
    """

    if not value.strip():
        return DEFAULT_UPLOAD_ATTEMPTS

    try:
        attempts = int(value)
    except ValueError as exc:
        raise GitCodeError("GITCODE_UPLOAD_ATTEMPTS must be an integer") from exc

    if attempts <= 0:
        raise GitCodeError("GITCODE_UPLOAD_ATTEMPTS must be greater than 0")
    return attempts


def discover_default_assets() -> list[Path]:
    """Discover files from the default release_assets directory.

    中：当用户没有提供 GITCODE_FILES 时，我们默认从 release_assets/ 目录取文件。
    这里只收集目录下的直接文件，不递归进入子目录，避免误传不相关内容。
    英：When GITCODE_FILES is not provided, files are collected from release_assets/.
    Only direct child files are included, without recursive traversal, to reduce the
    chance of uploading unrelated content.
    """

    if not DEFAULT_ASSET_DIR.exists():
        raise GitCodeError(
            f"Default asset directory does not exist: {DEFAULT_ASSET_DIR}"
        )
    if not DEFAULT_ASSET_DIR.is_dir():
        raise GitCodeError(
            f"Default asset path is not a directory: {DEFAULT_ASSET_DIR}"
        )

    files = sorted(path for path in DEFAULT_ASSET_DIR.iterdir() if path.is_file())
    if not files:
        raise GitCodeError(
            f"No files found in default asset directory: {DEFAULT_ASSET_DIR}"
        )
    return files


def validate_files(files: list[Path]) -> None:
    """Validate the artifact list before any network call starts.

    中：把文件存在性检查前置，可以尽早失败，避免 release 已创建但附件其实没准备好的情况。
    英：Validate files before making any network request so the script fails early
    instead of creating/updating a release and only later discovering missing files.
    """

    if not files:
        raise GitCodeError("No artifact files were resolved for upload")

    missing_files = [str(path) for path in files if not path.is_file()]
    if missing_files:
        raise GitCodeError(f"Artifact files do not exist: {', '.join(missing_files)}")


def build_headers(token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build common HTTP headers for GitCode API requests.

    中：这里集中处理鉴权和基础请求头，避免不同接口各自拼接造成不一致。
    英：Authentication and shared headers are assembled here to keep all API calls
    consistent.
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Release2GitCode/1.0",
    }
    if extra:
        headers.update(extra)
    return headers


def summarize_body(body: bytes) -> str:
    """Trim a response body for readable error logs.

    中：接口报错时返回体可能很长，这里截断到一个可读长度，既保留关键信息，也避免日志刷屏。
    英：Error responses can be verbose, so this helper keeps the useful part while
    preventing CI logs from becoming noisy.
    """

    text = body.decode("utf-8", errors="replace").strip()
    return text if len(text) <= 500 else f"{text[:500]}..."


def format_bytes(num_bytes: float) -> str:
    """Format a byte count using binary units.

    中：进度条里用 KiB/MiB/GiB 展示更符合大文件上传的直觉。
    英：Progress output uses KiB/MiB/GiB units for more intuitive large-file display.
    """

    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f}{unit}"
        value /= 1024
    return f"{value:.2f}TiB"


def format_duration(seconds: float) -> str:
    """Format seconds as a short ETA string."""

    total = max(int(seconds), 0)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def http_json(
    url: str,
    *,
    method: str = "GET",
    token: str,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | None = DEFAULT_TIMEOUT,
    operation: str,
) -> Any:
    """Send a JSON-oriented HTTP request and decode the response.

    中：虽然函数名叫 http_json，但它也兼容“响应头没写 JSON、实际内容却是 JSON 字符串”的情况，
    这是为了适配一些实现不够严格的接口。
    英：Despite the name, this helper also tolerates endpoints that forget to set a
    JSON content type but still return JSON text.
    """

    payload = None
    request_headers = build_headers(token, headers)
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        request_headers["Content-Type"] = "application/json; charset=utf-8"

    req = request.Request(url=url, data=payload, headers=request_headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw_body = response.read()
            if not raw_body:
                return None
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(raw_body.decode("utf-8"))
            text = raw_body.decode("utf-8", errors="replace")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    except error.HTTPError as exc:
        body = exc.read()
        raise GitCodeError(
            f"{operation} failed with HTTP {exc.code}: {summarize_body(body)}"
        ) from exc
    except error.URLError as exc:
        raise GitCodeError(f"{operation} failed: {exc.reason}") from exc


def release_url(config: Config, suffix: str = "") -> str:
    """Build a GitCode release API URL from config and an optional suffix.

    中：owner、repo 都会先做 URL 编码，避免命名空间或仓库名中存在特殊字符时拼接出错。
    英：owner and repo are URL-encoded first so special characters do not break the
    generated endpoint URL.
    """

    owner = parse.quote(config.owner, safe="")
    repo = parse.quote(config.repo, safe="")
    return f"{API_BASE}/repos/{owner}/{repo}/releases{suffix}"


def get_release_by_tag(config: Config) -> dict[str, Any] | None:
    """Fetch an existing release by tag.

    中：如果接口返回 404，这里不会直接报错，而是返回 None，让上层决定是否创建 release。
    英：A 404 is treated as "release does not exist yet" and converted to None so
    the caller can decide whether to create it.
    """

    tag = parse.quote(config.tag, safe="")
    url = release_url(config, f"/tags/{tag}")
    try:
        response = http_json(
            url,
            token=config.token,
            timeout=config.timeout_seconds,
            operation="Get release by tag",
        )
    except GitCodeError as exc:
        error_text = str(exc)
        if "HTTP 404" in error_text or "404 Release Not Found" in error_text:
            return None
        raise

    if isinstance(response, dict):
        return response
    raise GitCodeError(f"Get release by tag returned an unexpected payload: {response!r}")


def create_release(config: Config) -> dict[str, Any]:
    """Create a GitCode release for the configured tag.

    中：这里只提交当前脚本真正依赖的最小字段，避免对文档未明确的字段做多余假设。
    英：Only the minimum fields required by this script are sent, so we avoid making
    extra assumptions about undocumented release fields.
    """

    payload = {
        "tag_name": config.tag,
        "name": config.release_name,
        "body": config.release_body,
    }
    if config.target_branch:
        # 中：GitCode 的 Release 接口风格接近 GitHub/Gitee，通常使用 target_commitish
        # 指定目标分支或提交。这里按计划显式传入 nightly，并在接口不接受时直接失败。
        # 英：GitCode release APIs generally follow the GitHub/Gitee convention of
        # using target_commitish to select the target branch or commit. We pass it
        # explicitly and fail loudly if the server rejects it.
        payload["target_commitish"] = config.target_branch
    response = http_json(
        release_url(config),
        method="POST",
        token=config.token,
        data=payload,
        timeout=config.timeout_seconds,
        operation="Create release",
    )
    if isinstance(response, dict):
        return response
    raise GitCodeError(f"Create release returned an unexpected payload: {response!r}")


def update_release(config: Config, existing_release: dict[str, Any]) -> dict[str, Any]:
    """Update release metadata when the target release already exists.

    中：优先按 tag 更新；如果接口实现其实要求 id，则会自动退回到 id 再尝试一次。
    这是因为 GitCode 文档页能确认有更新接口，但返回/路径细节不够完整。
    英：The script first tries to update by tag. If the backend actually expects a
    numeric release id instead, it falls back to the id returned by the existing
    release payload.
    """

    payload = {
        "tag_name": config.tag,
        "name": config.release_name,
        "body": config.release_body,
    }

    candidates = [config.tag]
    release_id = existing_release.get("id")
    if release_id not in (None, ""):
        candidates.append(str(release_id))

    last_error: GitCodeError | None = None
    for candidate in candidates:
        suffix = f"/{parse.quote(candidate, safe='')}"
        try:
            response = http_json(
                release_url(config, suffix),
                method="PATCH",
                token=config.token,
                data=payload,
                timeout=config.timeout_seconds,
                operation=f"Update release ({candidate})",
            )
            if isinstance(response, dict):
                return response
            raise GitCodeError(f"Update release returned an unexpected payload: {response!r}")
        except GitCodeError as exc:
            last_error = exc
            if "HTTP 404" not in str(exc):
                raise

    raise last_error or GitCodeError("Update release failed")


def ensure_release(config: Config) -> dict[str, Any]:
    """Ensure the release exists and has the expected metadata.

    中：这是脚本的“幂等入口”。
    - 不存在则创建；
    - 存在但标题或描述变化则更新；
    - 完全一致则直接复用。

    英：This is the idempotent entrypoint for release state:
    - create it if missing;
    - update it if title/body changed;
    - reuse it as-is if already correct.
    """

    existing = get_release_by_tag(config)
    if existing is None:
        print(f"GitCode release {config.tag} not found, creating it.")
        return create_release(config)

    needs_update = (
        existing.get("name") != config.release_name
        or existing.get("body") != config.release_body
        or existing.get("tag_name") != config.tag
    )
    if needs_update:
        print(f"GitCode release {config.tag} exists, updating metadata.")
        return update_release(config, existing)

    print(f"GitCode release {config.tag} already exists, metadata is up to date.")
    return existing


def existing_attach_asset_names(release: dict[str, Any]) -> set[str]:
    """Collect uploaded attachment names from an existing release payload.

    中：只看 `type=attach` 的附件，源码包这类自动生成资源不参与重复上传判断。
    英：Only `type=attach` assets are considered for duplicate-upload detection;
    auto-generated source archives are ignored.
    """

    assets = release.get("assets")
    if not isinstance(assets, list):
        return set()

    names: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if str(asset.get("type") or "").lower() != "attach":
            continue
        name = str(asset.get("name") or "").strip()
        if name:
            names.add(name)
    return names


def extract_upload_target(response: Any) -> UploadTarget:
    """Normalize the upload target response from GitCode.

    中：GitCode 文档没有完整展示 upload_url 的响应体，所以这里接受几种常见形态：
    - 直接返回字符串 URL；
    - 返回对象，其中包含 url / upload_url；
    - 返回 multipart 需要的附加字段。

    英：GitCode does not fully document the upload_url payload, so this function
    accepts several common shapes:
    - a raw string URL;
    - an object containing url / upload_url;
    - optional multipart-related fields.
    """

    if isinstance(response, str):
        return UploadTarget(url=response)

    if not isinstance(response, dict):
        raise GitCodeError(f"Get upload URL returned an unexpected payload: {response!r}")

    upload_url = response.get("upload_url") or response.get("url")
    if not upload_url:
        raise GitCodeError(f"Upload URL missing in response: {response!r}")

    headers = response.get("headers") if isinstance(response.get("headers"), dict) else None
    form_fields = None
    for key in ("form_fields", "fields", "form", "data"):
        if isinstance(response.get(key), dict):
            form_fields = {str(k): str(v) for k, v in response[key].items()}
            break

    file_field_name = str(response.get("file_field_name") or response.get("file_field") or "file")
    filename_query_key = response.get("filename_query_key")
    if filename_query_key is not None:
        filename_query_key = str(filename_query_key)
    elif response.get("append_filename") is False:
        filename_query_key = None
    else:
        filename_query_key = "file_name"

    return UploadTarget(
        url=str(upload_url),
        method=str(response.get("method") or "PUT").upper(),
        headers=headers,
        form_fields=form_fields,
        file_field_name=file_field_name,
        filename_query_key=filename_query_key,
    )


def get_upload_target(config: Config, artifact_name: str) -> UploadTarget:
    """Fetch and normalize the upload endpoint for release assets.

    中：GitCode 的 upload_url 接口实际要求携带 file_name，所以这里按“每个文件请求一次”
    的方式获取上传地址，避免服务端直接返回参数缺失错误。
    英：GitCode's upload_url endpoint actually requires file_name, so the script
    requests one upload URL per artifact instead of fetching a single shared URL.

    中：这里按你找到的示例风格，优先使用 requests.get(..., params=...) 获取 upload_url。
    英：Following the sample style you found, this function now uses
    requests.get(..., params=...) to fetch the upload_url.
    """

    tag = parse.quote(config.tag, safe="")
    url = release_url(config, f"/{tag}/upload_url")
    headers = build_headers(config.token)
    params = {"file_name": artifact_name}

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=config.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise GitCodeError(
            f"Get release upload URL for {artifact_name} failed: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise GitCodeError(
            f"Get release upload URL for {artifact_name} failed with HTTP "
            f"{response.status_code}: {summarize_body(response.content)}"
        )

    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text

    return extract_upload_target(payload)


def append_filename_query(url: str, query_key: str | None, filename: str) -> str:
    """Append the filename into the upload URL query if needed.

    中：有些上传接口要求把文件名放到查询参数里；如果 URL 本身已经带了同名参数，就不重复追加。
    英：Some upload endpoints expect the file name as a query parameter. If the URL
    already contains that key, the function leaves it unchanged.
    """

    if not query_key:
        return url

    parsed = parse.urlsplit(url)
    query = parse.parse_qsl(parsed.query, keep_blank_values=True)
    existing_keys = {key for key, _ in query}
    if query_key not in existing_keys:
        query.append((query_key, filename))
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), parsed.fragment))


def upload_file(
    target: UploadTarget,
    artifact: Path,
    timeout_seconds: int | None,
    upload_attempts: int,
) -> Any:
    """Upload one artifact file to the resolved upload endpoint.

    中：函数会根据 UploadTarget 的信息自动决定上传方式：
    - 如果存在 form_fields，则使用 multipart/form-data；
    - 否则直接发送文件二进制内容。

    英：The upload mode is chosen automatically from UploadTarget:
    - use multipart/form-data when form_fields are present;
    - otherwise send the raw file bytes directly.
    """

    content_type = mimetypes.guess_type(artifact.name)[0] or "application/octet-stream"
    upload_url = append_filename_query(target.url, target.filename_query_key, artifact.name)
    method = target.method.upper()
    last_error: GitCodeError | None = None

    for attempt in range(1, upload_attempts + 1):
        if upload_attempts > 1:
            print(f"Attempt {attempt}/{upload_attempts} for {artifact.name}")

        headers = {"User-Agent": "Release2GitCode/1.0"}
        if target.headers:
            headers.update(target.headers)

        if target.form_fields:
            multipart_probe = MultipartUploadStream(
                fields=target.form_fields,
                file_field_name=target.file_field_name,
                artifact=artifact,
                content_type=content_type,
                reporter=ProgressReporter(artifact.name, 1),
            )
            reporter = ProgressReporter(artifact.name, len(multipart_probe))
            multipart_stream = MultipartUploadStream(
                fields=target.form_fields,
                file_field_name=target.file_field_name,
                artifact=artifact,
                content_type=content_type,
                reporter=reporter,
            )
            body = multipart_stream
            headers["Content-Type"] = multipart_stream.content_type_header
            headers["Content-Length"] = str(len(multipart_stream))
        else:
            raw_probe = RawUploadStream(
                artifact=artifact,
                reporter=ProgressReporter(artifact.name, 1),
            )
            reporter = ProgressReporter(artifact.name, len(raw_probe))
            raw_stream = RawUploadStream(
                artifact=artifact,
                reporter=reporter,
            )
            body = raw_stream
            headers.setdefault("Content-Type", content_type)
            headers["Content-Length"] = str(len(raw_stream))

        try:
            response = requests.request(
                method,
                upload_url,
                headers=headers,
                data=body,
                timeout=timeout_seconds,
            )
            reporter.finish()
        except requests.RequestException as exc:
            print()
            last_error = GitCodeError(f"Upload artifact {artifact.name} failed: {exc}")
            if attempt < upload_attempts:
                print(f"Retrying {artifact.name} after transport failure...")
                continue
            raise last_error from exc

        if response.status_code >= 500:
            last_error = GitCodeError(
                f"Upload artifact {artifact.name} failed with HTTP {response.status_code}: "
                f"{summarize_body(response.content)}"
            )
            if attempt < upload_attempts:
                print(f"Retrying {artifact.name} after server error...")
                continue
            raise last_error

        if response.status_code >= 400:
            raise GitCodeError(
                f"Upload artifact {artifact.name} failed with HTTP {response.status_code}: "
                f"{summarize_body(response.content)}"
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    raise last_error or GitCodeError(f"Upload artifact {artifact.name} failed")


def build_download_url(config: Config, file_name: str) -> str:
    """Construct a predictable fallback download URL for a release asset.

    中：即使上传接口返回值里没有下载链接，我们也能根据文档中的下载地址规则拼出一个候选链接。
    英：If the upload response does not provide a download URL, this function builds
    a predictable fallback URL using the documented asset download route.
    """

    owner = parse.quote(config.owner, safe="")
    repo = parse.quote(config.repo, safe="")
    tag = parse.quote(config.tag, safe="")
    quoted_name = parse.quote(file_name, safe="")
    return (
        f"{API_BASE}/repos/{owner}/{repo}/releases/{tag}/attach_files/{quoted_name}/download"
    )


def maybe_result_url(result: Any) -> str | None:
    """Extract a useful URL from an upload response when available.

    中：不同接口实现返回的字段名可能不同，所以这里尝试几个常见字段。
    英：Different implementations may return different field names, so this helper
    checks a few common URL keys.
    """

    if isinstance(result, dict):
        for key in ("browser_download_url", "download_url", "url"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(result, str) and result.startswith("http"):
        return result
    return None


def main() -> int:
    """Program entrypoint.

    中：执行顺序固定为：
    1. 读取配置；
    2. 确保 Release 存在；
    3. 获取上传地址；
    4. 逐个上传文件；
    5. 输出结果或错误。

    英：Execution order:
    1. load config;
    2. ensure the release exists;
    3. fetch the upload endpoint;
    4. upload files one by one;
    5. print results or errors.
    """

    try:
        config = load_config()
        print(f"Repository: {config.repo_url}")
        print(f"Release tag: {config.tag}")
        if config.target_branch:
            print(
                f"Using target branch {config.target_branch} for release creation when needed."
            )
        if config.skip_release_ensure:
            print(
                f"Skipping release creation/update for tag {config.tag} because "
                "GITCODE_SKIP_RELEASE_ENSURE is enabled."
            )
            release = get_release_by_tag(config)
            if release is None:
                raise GitCodeError(
                    f"Release {config.tag} does not exist and GITCODE_SKIP_RELEASE_ENSURE is enabled."
                )
        else:
            release = ensure_release(config)

        uploaded_asset_names = existing_attach_asset_names(release)
        if uploaded_asset_names:
            print(
                f"Found {len(uploaded_asset_names)} existing attached asset(s) in release {config.tag}."
            )

        # 中：这里打印最终解析出的文件数量，方便确认脚本到底是走了 GITCODE_FILES，
        # 还是走了默认的 release_assets/ 扫描逻辑。
        # 英：Printing the resolved file count helps confirm whether the script used
        # GITCODE_FILES or the default release_assets/ discovery path.
        print(f"Uploading {len(config.files)} artifact(s) to GitCode release {config.tag}.")
        for artifact in config.files:
            if artifact.name in uploaded_asset_names:
                print(
                    f"Skipping {artifact.name} because it already exists in release {config.tag}."
                )
                continue
            print(f"Uploading {artifact} ...")
            upload_target = get_upload_target(config, artifact.name)
            result = upload_file(
                upload_target,
                artifact,
                config.timeout_seconds,
                config.upload_attempts,
            )
            result_url = maybe_result_url(result) or build_download_url(config, artifact.name)
            print(f"Uploaded {artifact.name}: {result_url}")
            uploaded_asset_names.add(artifact.name)

        print("All artifacts uploaded successfully.")
        return 0
    except GitCodeError as exc:
        eprint(f"ERROR: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive fallback
        eprint(f"UNEXPECTED ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
