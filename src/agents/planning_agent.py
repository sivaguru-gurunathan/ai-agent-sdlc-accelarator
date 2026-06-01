import os
import re
from src.agents.base_agent import BaseAgent


class PlanningAgent(BaseAgent):
    def __init__(self, model_id: str):
        super().__init__(name="planning", description="Project planning agent", model_id=model_id)

    def run(self, input_data: dict) -> dict:
        repo_analysis = input_data.get("repo_analysis", {})
        options = input_data.get("options", {})
        summary = repo_analysis.get("summary", "")
        repo_name = repo_analysis.get("repo_name", "repository")

        system_prompt = (
            "You are an expert software architect."
            " Generate a complete planning document for the repository analysis provided."
            " Return a structured Markdown document containing the following sections:"
            " Project Overview, Current Architecture, Recommended Tech Stack, Feature Breakdown,"
            " Implementation Plan, Deployment Recommendations."
            " Include all requested sections explicitly."
        )

        prompt = (
            f"Given the repository '{repo_name}', produce a full planning document. "
            f"Use the analysis summary and file list to infer architecture, languages, and feature ideas.\n\n"
            f"Repository summary:\n{summary}\n\n"
            f"Options:\n{options}\n\n"
            "Return the response as Markdown with headings and numbered implementation steps."
        )

        planning_document = self.invoke_claude(prompt, system_prompt)
        sections = self._extract_sections(planning_document)
        return {
            "planning_document": planning_document,
            "sections": sections,
        }

    def _extract_sections(self, markdown: str) -> dict:
        results = {}
        current_key = None
        current_lines = []
        for line in markdown.splitlines():
            heading_match = re.match(r"^#{1,3}\s+(.*)", line)
            if heading_match:
                if current_key:
                    results[current_key] = "\n".join(current_lines).strip()
                current_key = heading_match.group(1).strip().lower().replace(" ", "_")
                current_lines = []
            elif current_key:
                current_lines.append(line)
        if current_key:
            results[current_key] = "\n".join(current_lines).strip()
        return results
