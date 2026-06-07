import os
import shutil
import re
from pathlib import Path
from git import Repo, GitCommandError

GITHUB_URL_REGEX = r"^https://github\.com/[^/]+/[^/]+"


def normalize_github_url(url: str) -> str:
    """Strip branch/path suffixes so users can paste browser URLs directly."""
    url = url.strip().rstrip("/")
    # Remove .git suffix, then keep only owner/repo
    url = re.sub(r"\.git$", "", url)
    m = re.match(r"(https://github\.com/[^/]+/[^/]+)", url)
    return m.group(1) if m else url


def validate_github_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    return re.match(GITHUB_URL_REGEX, url.strip()) is not None


def extract_repo_name(url: str) -> str:
    normalized = url.strip()
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    parts = normalized.split("github.com/")
    return parts[-1].rstrip("/") if len(parts) == 2 else normalized


def clone_repo(url: str, token: str, dest_dir: str) -> str:
    repo_name = extract_repo_name(url)
    target_path = Path(dest_dir) / repo_name.replace("/", "_")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        shutil.rmtree(target_path)
    repo_url = url
    real_token = token and not token.startswith("REPLACE_")
    if real_token:
        repo_url = url.replace("https://github.com/", f"https://{token}@github.com/")
    try:
        Repo.clone_from(repo_url, target_path)
        return str(target_path)
    except GitCommandError as exc:
        raise RuntimeError(f"Failed to clone repository: {exc}") from exc


def cleanup_repo(path: str):
    if path and os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def extract_repo_context(github_url: str, token: str, temp_dir: str = "/tmp/repos") -> str:
    """Clone a repo, extract its architectural context as plain text, then clean up."""
    repo_path = clone_repo(github_url, token, temp_dir)
    try:
        return _build_context(repo_path)
    finally:
        cleanup_repo(repo_path)


def _build_context(repo_path: str) -> str:
    MAX_FILE = 3000
    parts = []

    # Config / manifest files that reveal the stack and dependencies
    for fname in ("package.json", "angular.json", "tsconfig.json",
                  "pom.xml", "build.gradle", "pyproject.toml", "go.mod"):
        fpath = os.path.join(repo_path, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8", errors="replace") as f:
                parts.append(f"### {fname}\n{f.read()[:MAX_FILE]}")

    # Architecture / onboarding docs
    for fname in ("CLAUDE.md", "README.md", "ARCHITECTURE.md",
                  os.path.join(".claude", "CLAUDE.md"),
                  os.path.join("docs", "architecture.md")):
        fpath = os.path.join(repo_path, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8", errors="replace") as f:
                parts.append(f"### {fname}\n{f.read()[:MAX_FILE]}")
            break

    # Folder trees
    parts.append("### Root structure\n" + _tree(repo_path, max_depth=2))
    src = os.path.join(repo_path, "src")
    if os.path.exists(src):
        parts.append("### src/ structure\n" + _tree(src, max_depth=4))

    return "\n\n".join(parts)[:12000]


def _tree(path: str, prefix: str = "", max_depth: int = 4, depth: int = 0) -> str:
    if depth > max_depth:
        return ""
    skip = {".git", "node_modules", "dist", "__pycache__", ".angular",
            "coverage", ".nyc_output", "build", ".venv", "venv"}
    try:
        entries = sorted(e for e in os.listdir(path)
                         if e not in skip and not e.startswith("."))
    except PermissionError:
        return ""
    lines = []
    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        connector = "└── " if last else "├── "
        lines.append(prefix + connector + entry)
        full = os.path.join(path, entry)
        if os.path.isdir(full) and depth < max_depth:
            ext = "    " if last else "│   "
            sub = _tree(full, prefix + ext, max_depth, depth + 1)
            if sub:
                lines.append(sub)
    return "\n".join(lines)
