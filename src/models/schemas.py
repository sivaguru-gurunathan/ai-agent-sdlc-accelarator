from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from src.utils.github_utils import validate_github_url


@dataclass
class AnalyzeRequest:
    github_url: str
    agent_type: str
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
    github_url = data.get("github_url")
    agent_type = data.get("agent_type")
    options = data.get("options", {})
    if not github_url:
        raise ValueError("Missing required field: github_url")
    if not isinstance(github_url, str) or not validate_github_url(github_url):
        raise ValueError("Invalid github_url value.")
    if not agent_type or not isinstance(agent_type, str):
        raise ValueError("Missing or invalid field: agent_type")
    if not isinstance(options, dict):
        raise ValueError("Options must be an object.")
    return AnalyzeRequest(github_url=github_url.strip(), agent_type=agent_type.strip(), options=options)
