import os
import logging
from pathlib import Path
from src.agents.base_agent import BaseAgent
from src.utils.github_utils import clone_repo, cleanup_repo, extract_repo_name

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".json": "JSON",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".txt": "Text",
    ".ini": "INI",
    ".cfg": "Config",
    ".sh": "Shell",
}

SKIP_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build"}
MAX_LINES = 60
MAX_SUMMARY_CHARS = 8000


class RepositoryAgent(BaseAgent):
    def __init__(self, model_id: str):
        super().__init__(name="repository", description="Repository analysis agent", model_id=model_id)

    def run(self, input_data: dict) -> dict:
        github_url = input_data.get("github_url")
        token = os.getenv("GITHUB_TOKEN")
        dest_dir = os.getenv("TEMP_CLONE_DIR", "/tmp/repos")
        repo_path = None
        try:
            repo_path = clone_repo(github_url, token, dest_dir)
            file_tree = []
            file_contents = {}
            languages = set()
            total_summary = []
            summary_chars = 0

            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                relative_root = os.path.relpath(root, repo_path)
                for filename in files:
                    if any(part in SKIP_DIRS for part in Path(root).parts):
                        continue
                    path = Path(root) / filename
                    extension = path.suffix.lower()
                    if extension not in TEXT_EXTENSIONS:
                        continue
                    relative_path = os.path.join(relative_root, filename) if relative_root != "." else filename
                    file_tree.append(relative_path)
                    languages.add(TEXT_EXTENSIONS.get(extension, "Other"))
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as handle:
                            lines = handle.readlines()[:MAX_LINES]
                            content = "".join(lines).strip()
                            if len(content) > 0:
                                file_contents[relative_path] = content
                                if summary_chars < MAX_SUMMARY_CHARS:
                                    available = MAX_SUMMARY_CHARS - summary_chars
                                    excerpt = content[:available]
                                    total_summary.append(f"### {relative_path}\n{excerpt}\n")
                                    summary_chars += len(excerpt)
                    except (OSError, UnicodeError):
                        logger.warning("Skipping unreadable file: %s", path)

            stats = {
                "file_count": len(file_tree),
                "language_count": len(languages),
            }
            return {
                "repo_name": extract_repo_name(github_url),
                "repo_path": repo_path,
                "file_tree": file_tree,
                "file_contents": file_contents,
                "languages": sorted(languages),
                "stats": stats,
                "summary": "\n".join(total_summary),
            }
        finally:
            if repo_path:
                cleanup_repo(repo_path)
