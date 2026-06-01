import os
import shutil
import re
from pathlib import Path
from git import Repo, GitCommandError

GITHUB_URL_REGEX = r"^https://github\.com/[^/]+/[^/]+(?:\.git)?$"


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
    if token:
        repo_url = url.replace("https://github.com/", f"https://{token}@github.com/")
    try:
        Repo.clone_from(repo_url, target_path)
        return str(target_path)
    except GitCommandError as exc:
        raise RuntimeError(f"Failed to clone repository: {exc}") from exc


def cleanup_repo(path: str):
    if path and os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)
