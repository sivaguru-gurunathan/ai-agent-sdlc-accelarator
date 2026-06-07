import os
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import logging
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from src.utils.bedrock_utils import test_bedrock_connection
from src.models.schemas import validate_request
from src.agents.orchestrator import Orchestrator
from src.agents.figma_agent import FigmaAgent
from src.utils.figma_utils import validate_figma_url
from src.utils.github_utils import extract_repo_context, validate_github_url as _validate_gh

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
    figma_url = request_data.figma_url
    agent_type = request_data.agent_type
    options = request_data.options or {}

    try:
        result = orchestrator.run_analysis(github_url, agent_type, options, figma_url=figma_url)
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("Analysis failed")
        return jsonify({"status": "error", "message": "Analysis failed.", "detail": str(exc)}), 500


@app.route("/api/upload-api-doc", methods=["POST"])
def upload_api_doc():
    from src.utils.doc_utils import parse_document, SUPPORTED_EXTENSIONS
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file attached."}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"status": "error", "message": "Empty file."}), 400
    ext = file.filename.lower()
    if not any(ext.endswith(e) for e in SUPPORTED_EXTENSIONS):
        return jsonify({"status": "error", "message": f"Unsupported type. Upload one of: {', '.join(SUPPORTED_EXTENSIONS)}"}), 400
    try:
        text = parse_document(file)
        return jsonify({"status": "success", "filename": file.filename, "text": text, "char_count": len(text)}), 200
    except Exception as exc:
        logger.exception("Document parse failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/figma/read-repo", methods=["POST"])
def figma_read_repo():
    data = request.get_json(force=True) or {}
    github_url = data.get("github_url", "").strip()
    if not github_url or not _validate_gh(github_url):
        return jsonify({"status": "error", "message": "Invalid or missing github_url."}), 400
    try:
        token = os.getenv("GITHUB_TOKEN", "")
        context = extract_repo_context(github_url, token)
        return jsonify({"status": "success", "context": context}), 200
    except Exception as exc:
        logger.exception("Repo context extraction failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


_jobs: dict = {}  # job_id -> {status, result, error, tick}


@app.route("/api/figma/analyze", methods=["POST"])
def figma_analyze():
    import threading, uuid
    data = request.get_json(force=True) or {}
    figma_url = data.get("figma_url", "").strip()
    logger.info("Figma analyze request — url: %r", figma_url)
    if not figma_url or not validate_figma_url(figma_url):
        logger.warning("Figma URL validation failed for: %r", figma_url)
        return jsonify({"status": "error", "message": f"Invalid Figma URL: {figma_url!r}. Expected format: https://www.figma.com/design/KEY/Name"}), 400

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None, "tick": 0, "type": "analyze"}

    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5")
    agent = FigmaAgent(model_id=model_id)

    def run():
        import time as _t, threading as _th
        stop_hb = _th.Event()
        def heartbeat():
            while not stop_hb.is_set():
                _t.sleep(2)
                if _jobs.get(job_id, {}).get("status") == "running":
                    _jobs[job_id]["tick"] = _jobs[job_id].get("tick", 0) + 1
        _th.Thread(target=heartbeat, daemon=True).start()
        try:
            result = agent.analyze_screens(figma_url)
            stop_hb.set()
            _jobs[job_id]["result"] = result
            _jobs[job_id]["status"] = "done"
        except Exception as exc:
            stop_hb.set()
            logger.exception("Figma screen analysis failed")
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(exc)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started", "job_id": job_id}), 202


@app.route("/api/figma/generate", methods=["POST"])
def figma_generate():
    import threading, uuid
    data = request.get_json(force=True) or {}
    design_summary = data.get("design_summary", "").strip()
    design_name = data.get("design_name", "App").strip()
    endpoints = data.get("endpoints", "").strip()
    doc_type = int(data.get("doc_type", 1))
    repo_context = data.get("repo_context", "")
    user_requirements = data.get("user_requirements", "")

    if not design_summary or not endpoints:
        return jsonify({"status": "error", "message": "Missing design_summary or endpoints."}), 400

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "text": "", "error": None, "tick": 0}

    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5")
    agent = FigmaAgent(model_id=model_id)

    def run():
        import time as _t
        try:
            # Heartbeat thread so polls show the job is alive even during the blocking call
            import threading as _th
            stop_hb = _th.Event()
            def heartbeat():
                while not stop_hb.is_set():
                    _t.sleep(2)
                    if _jobs.get(job_id, {}).get("status") == "running":
                        _jobs[job_id]["tick"] = _jobs[job_id].get("tick", 0) + 1
            _th.Thread(target=heartbeat, daemon=True).start()

            text = agent.generate_doc(
                doc_type, design_summary, design_name,
                endpoints, repo_context, user_requirements
            )
            stop_hb.set()
            _jobs[job_id]["text"] = text
            _jobs[job_id]["status"] = "done"
        except Exception as exc:
            logger.exception("Doc generation failed")
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(exc)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started", "job_id": job_id}), 202


@app.route("/api/figma/job/<job_id>", methods=["GET"])
def figma_job_status(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"status": "error", "error": "Job not found"}), 404
    job_type = job.get("type", "generate")
    if job_type == "analyze":
        return jsonify({
            "status": job["status"],
            "tick": job.get("tick", 0),
            "result": job["result"] if job["status"] == "done" else None,
            "error": job["error"],
        }), 200
    # generate type
    text = job.get("text", "") or ""
    words = len(text.split()) if text else 0
    return jsonify({
        "status": job["status"],
        "words": words,
        "tick": job.get("tick", 0),
        "text": text if job["status"] == "done" else "",
        "error": job["error"],
    }), 200


@app.route("/", methods=["GET"])
def index():
    static_dir = Path(__file__).resolve().parents[0] / "static"
    resp = send_from_directory(str(static_dir), "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.errorhandler(404)
def handle_404(error):
    return jsonify({"status": "error", "message": "Resource not found."}), 404

@app.errorhandler(500)
def handle_500(error):
    return jsonify({"status": "error", "message": "Internal server error."}), 500

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
