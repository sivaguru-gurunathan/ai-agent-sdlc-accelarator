import os
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from src.utils.bedrock_utils import test_bedrock_connection
from src.models.schemas import validate_request
from src.agents.orchestrator import Orchestrator

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

orchestrator = Orchestrator()

@app.route("/api/health", methods=["GET"])
def health():
    bedrock_ok = test_bedrock_connection()
    status = "ok" if bedrock_ok else "error"
    response = {
        "status": "ok" if bedrock_ok else "error",
        "bedrock": "connected" if bedrock_ok else "disconnected",
    }
    return jsonify(response), 200 if bedrock_ok else 500

@app.route("/api/agents", methods=["GET"])
def list_agents():
    return jsonify({"agents": orchestrator.get_available_agents()}), 200

@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(force=True)
        request_data = validate_request(data)
    except ValueError as exc:
        logger.error("Request validation failed: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to parse request")
        return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

    github_url = request_data.github_url
    agent_type = request_data.agent_type
    options = request_data.options or {}

    try:
        result = orchestrator.run_analysis(github_url, agent_type, options)
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("Analysis failed")
        return jsonify({"status": "error", "message": "Analysis failed.", "detail": str(exc)}), 500


@app.route("/", methods=["GET"])
def index():
    # Serve the single-file UI from src/static/index.html
    static_dir = Path(__file__).resolve().parents[0] / "static"
    return send_from_directory(str(static_dir), "index.html")

@app.errorhandler(404)
def handle_404(error):
    return jsonify({"status": "error", "message": "Resource not found."}), 404

@app.errorhandler(500)
def handle_500(error):
    return jsonify({"status": "error", "message": "Internal server error."}), 500

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
