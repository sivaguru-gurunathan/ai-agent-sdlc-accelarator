import logging
import os
from abc import ABC, abstractmethod
from botocore.exceptions import BotoCoreError, ClientError
from src.utils.bedrock_utils import get_bedrock_client, format_messages
import json

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, name: str, description: str, model_id: str):
        self.name = name
        self.description = description
        self.model_id = model_id

    def invoke_claude(self, prompt: str, system_prompt: str) -> str:
        client = get_bedrock_client()
        payload = format_messages(prompt, system_prompt)
        # Use top-level Anthropic request fields required by Bedrock.
        payload["max_tokens"] = 1500
        payload["anthropic_version"] = "bedrock-2023-05-31"
        payload["temperature"] = 0.2
        payload["stop_sequences"] = []
        logger.info("Invoking Bedrock with payload: %s", json.dumps(payload, indent=2))
        try:
            response = client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload),
            )
            body = response.get("body")
            if hasattr(body, "read"):
                body = body.read()
            if isinstance(body, (bytes, bytearray)):
                body = body.decode("utf-8")
            parsed = json.loads(body)
            return parsed["content"][0]["text"]
        except (BotoCoreError, ClientError) as exc:
            logger.exception("Bedrock invocation failed")
            raise RuntimeError(f"Claude invocation failed: {exc}") from exc

    @abstractmethod
    def run(self, input_data: dict) -> dict:
        raise NotImplementedError()
