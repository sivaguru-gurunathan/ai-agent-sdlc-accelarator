from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from src.utils.github_utils import validate_github_url, normalize_github_url
from src.utils.figma_utils import validate_figma_url


@dataclass
class AnalyzeRequest:
    agent_type: str
    github_url: Optional[str] = None
    figma_url: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyzeResponse:
    status: str
    repo_name: Optional[str] = None
    planning_document: Optional[str] = None
    sections: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None


def validate_request(data: dict) -> AnalyzeRequest:
    if not isinstance(data, dict):
        raise ValueError("Request payload must be a JSON object.")
    agent_type = data.get("agent_type")
    github_url = data.get("github_url")
    figma_url = data.get("figma_url")
    options = data.get("options", {})

    if not agent_type or not isinstance(agent_type, str):
        raise ValueError("Missing or invalid field: agent_type")
    if not isinstance(options, dict):
        raise ValueError("Options must be an object.")

    if agent_type == "figma":
        if not figma_url or not isinstance(figma_url, str) or not validate_figma_url(figma_url):
            raise ValueError("Invalid or missing figma_url for figma agent type.")
    else:
        if not github_url:
            raise ValueError("Missing required field: github_url")
        if not isinstance(github_url, str) or not validate_github_url(github_url):
            raise ValueError("Invalid github_url value. Use: https://github.com/owner/repo")
        github_url = normalize_github_url(github_url)

    return AnalyzeRequest(
        agent_type=agent_type.strip(),
        github_url=github_url.strip() if github_url else None,
        figma_url=figma_url.strip() if figma_url else None,
        options=options,
    )
