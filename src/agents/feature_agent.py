import json
import re
from src.agents.base_agent import BaseAgent


class FeatureAgent(BaseAgent):
    def __init__(self, model_id: str):
        super().__init__(name="feature", description="Feature planning agent", model_id=model_id)

    def run(self, input_data: dict) -> dict:
        repo_analysis = input_data.get("repo_analysis", {})
        planning_document = input_data.get("planning_document", "")
        system_prompt = (
            "You are an AI product manager and feature spec expert."
            " Review the repository analysis and the generated planning document."
            " Return a JSON array of proposed features in a ```json code block."
            " Each feature object must include name, description, acceptance_criteria, and effort_estimate."
        )

        prompt = (
            "Based on the repository analysis and planning document, generate a list of high-value features.\n\n"
            f"Repository summary:\n{repo_analysis.get('summary', '')}\n\n"
            f"Planning document:\n{planning_document}\n\n"
            "Output only valid JSON inside a ```json code block."
        )

        raw_output = self.invoke_claude(prompt, system_prompt)
        json_text = self._extract_json(raw_output)
        try:
            features = json.loads(json_text)
        except json.JSONDecodeError:
            raise ValueError("Unable to parse JSON feature output from Claude.")
        return {"features": features}

    def _extract_json(self, text: str) -> str:
        match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
        if match:
            return match.group(1)
        match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if match:
            return match.group(1)
        raise ValueError("JSON block not found in Claude response.")
