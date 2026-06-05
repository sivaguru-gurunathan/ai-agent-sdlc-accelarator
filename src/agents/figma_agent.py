import os
from src.agents.base_agent import BaseAgent
from src.utils.figma_utils import extract_file_key, fetch_figma_file, extract_design_summary


class FigmaAgent(BaseAgent):
    def __init__(self, model_id: str):
        super().__init__(name="figma", description="Figma design analysis agent", model_id=model_id)

    def run(self, input_data: dict) -> dict:
        figma_url = input_data.get("figma_url")
        token = os.getenv("FIGMA_TOKEN")
        if not token:
            raise RuntimeError("FIGMA_TOKEN environment variable is not set.")

        file_key = extract_file_key(figma_url)
        figma_data = fetch_figma_file(file_key, token)
        design_summary = extract_design_summary(figma_data)

        screen_count = sum(
            1
            for page in figma_data.get("document", {}).get("children", [])
            for child in page.get("children", [])
            if child.get("type") == "FRAME"
        )

        system_prompt = (
            "You are a product manager and software architect reviewing a Figma design."
            " Based on the screen names, UI text, and components provided, generate a concise planning document."
            " Return Markdown with exactly these five sections:"
            " ## Product Overview, ## Screens & User Flows, ## Key Features, ## Suggested API Endpoints, ## Dev Tasks."
            " Be specific and actionable. Each section: 3-6 bullet points. Total response under 400 words."
        )

        prompt = (
            f"Analyze this Figma design and produce a developer planning document.\n\n"
            f"{design_summary}\n\n"
            "Infer user flows from screen names and text labels. "
            "List REST API endpoints a backend developer would need to implement. "
            "List dev tasks as actionable items a developer can pick up directly."
        )

        planning_document = self.invoke_claude(prompt, system_prompt)
        return {
            "planning_document": planning_document,
            "design_name": figma_data.get("name", "Figma Design"),
            "screen_count": screen_count,
        }
