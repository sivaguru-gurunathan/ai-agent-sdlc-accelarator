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
            "You are a senior engineer writing a brief repository briefing for developers and tech leads."
            " Be concise — no filler, no recommendations, no implementation plans."
            " Use only what you can directly observe in the code provided."
            " Return Markdown with exactly these four sections:"
            " ## What it does, ## Tech Stack, ## Key Modules, ## How to Run."
            " Each section should be 3-6 bullet points. Total response must stay under 400 words."
        )

        prompt = (
            f"Write a concise briefing for the repository '{repo_name}'.\n\n"
            f"Source files:\n{summary}\n\n"
            "Cover: what the project does, languages and frameworks used, the main modules and their role, "
            "and how to start or run it. Stick to facts visible in the code — no guessing."
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
