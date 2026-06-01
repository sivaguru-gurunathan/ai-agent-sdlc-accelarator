import os
import json
import boto3
from botocore.exceptions import BotoCoreError, ClientError


def get_bedrock_client():
    region = os.getenv("AWS_REGION")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    session_kwargs = {
        "region_name": region,
    }
    if access_key and secret_key:
        session_kwargs["aws_access_key_id"] = access_key
        session_kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("bedrock-runtime", **session_kwargs)


def test_bedrock_connection():
    model_id = os.getenv("BEDROCK_MODEL_ID")
    if not model_id:
        return False
    try:
        # Use the management Bedrock client to verify API access and permissions
        region = os.getenv("AWS_REGION")
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        kwargs = {"region_name": region}
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        admin_client = boto3.client("bedrock", **kwargs)
        # A lightweight call to list foundation models confirms connectivity
        _ = admin_client.list_foundation_models()
        return True
    except (BotoCoreError, ClientError, ValueError):
        return False


def format_messages(prompt: str, system_prompt: str):
    return {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
        "system": [{"type": "text", "text": system_prompt}],
    }
