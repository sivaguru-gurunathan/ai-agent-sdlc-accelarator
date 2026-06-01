import os
import logging
from src.agents.repository_agent import RepositoryAgent
from src.agents.planning_agent import PlanningAgent
from src.agents.feature_agent import FeatureAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5")
        self.available_agents = [
            {"id": "planning", "name": "Project Planning", "description": "High-level architecture and planning"},
            {"id": "feature", "name": "Feature Planning", "description": "Feature specifications"},
            {"id": "snapshot", "name": "Repository Snapshot", "description": "Codebase documentation"},
        ]

    def get_available_agents(self):
        return self.available_agents

    def run_analysis(self, github_url: str, agent_type: str, options: dict) -> dict:
        response = {"status": "success", "agent_used": agent_type, "metadata": {}, "sections": {}, "planning_document": None}
        repo_agent = RepositoryAgent(model_id=self.model_id)
        planning_agent = PlanningAgent(model_id=self.model_id)
        feature_agent = FeatureAgent(model_id=self.model_id)

        try:
            logger.info("Starting repository analysis")
            repo_analysis = repo_agent.run({"github_url": github_url})
            response["repo_name"] = repo_analysis.get("repo_name")
            response["metadata"]["files_analyzed"] = repo_analysis.get("stats", {}).get("file_count", 0)
            response["metadata"]["languages"] = repo_analysis.get("languages", [])
            response["metadata"]["repo_analysis"] = {
                "file_tree_count": len(repo_analysis.get("file_tree", []))
            }
            response["metadata"]["agent_used"] = agent_type
        except Exception as exc:
            logger.exception("Repository analysis failed")
            return {"status": "error", "message": "Repository analysis failed.", "detail": str(exc)}

        if agent_type == "snapshot":
            response["planning_document"] = "Repository analysis complete."
            response["sections"] = {"overview": repo_analysis.get("summary", "")}
            return response

        try:
            logger.info("Starting planning agent")
            planning_result = planning_agent.run({"repo_analysis": repo_analysis, "options": options})
            response["planning_document"] = planning_result.get("planning_document")
            response["sections"] = planning_result.get("sections", {})
        except Exception as exc:
            logger.exception("Planning agent failed")
            response["status"] = "warning"
            response["message"] = "Planning generation failed; repository analysis succeeded."
            response["detail"] = str(exc)
            return response

        if agent_type == "feature":
            try:
                logger.info("Starting feature agent")
                feature_result = feature_agent.run({"repo_analysis": repo_analysis, "planning_document": response["planning_document"]})
                response["features"] = feature_result.get("features", [])
            except Exception as exc:
                logger.exception("Feature agent failed")
                response["status"] = "warning"
                response["message"] = "Feature extraction failed; planning succeeded."
                response["detail"] = str(exc)

        return response
