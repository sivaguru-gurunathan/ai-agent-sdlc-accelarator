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

    def invoke_claude(self, prompt: str, system_prompt: str, max_tokens: int = 1500) -> str:
        client = get_bedrock_client()
        payload = format_messages(prompt, system_prompt)
        payload["max_tokens"] = max_tokens
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

    def stream_claude(self, prompt: str, system_prompt: str, max_tokens: int = 4000):
        """Yield text chunks from Claude as they arrive via Bedrock streaming."""
        client = get_bedrock_client(streaming=True)
        payload = format_messages(prompt, system_prompt)
        payload["max_tokens"] = max_tokens
        payload["anthropic_version"] = "bedrock-2023-05-31"
        payload["temperature"] = 0.2
        payload["stop_sequences"] = []
        try:
            response = client.invoke_model_with_response_stream(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload),
            )
            event_stream = response.get("body")
            for event in event_stream:
                chunk = event.get("chunk")
                if not chunk:
                    continue
                raw = chunk.get("bytes")
                if not raw:
                    continue
                data = json.loads(raw)
                if data.get("type") == "content_block_delta":
                    text = data.get("delta", {}).get("text", "")
                    if text:
                        yield text
        except Exception as exc:
            logger.exception("Bedrock streaming failed")
            raise RuntimeError(f"Streaming failed: {exc}") from exc

    @abstractmethod
    def run(self, input_data: dict) -> dict:
        raise NotImplementedError()
