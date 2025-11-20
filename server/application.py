import json
import logging
import os
import uuid

from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from langchain_core.messages import HumanMessage
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator

from agents import market_graph
from database import db_handler

load_dotenv()

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("market_intel.application")
MAX_QUERY_CHARS = 800
POLICY_VIOLATION_MESSAGE = (
    "This request can't be processed because it violates our usage guidelines. "
    "Try rephrasing with a professional market or competitive research question."
)
moderation_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) if os.environ.get("OPENAI_API_KEY") else None

MARKET_KEYWORDS = [
    "market",
    "competitor",
    "competitive",
    "pricing",
    "go-to-market",
    "gtm",
    "analysis",
    "research",
    "benchmark",
    "positioning",
    "product comparison",
    "sales strategy",
]
OUT_OF_SCOPE_MESSAGE = (
    "Thanks for your request! This assistant focuses on market and competitive "
    "research tasks (pricing, positioning, competitor insights, etc.). "
    "Please submit a market intelligence query so I can help."
)


def is_market_intel_query(query: str) -> bool:
    normalized = query.lower()
    return any(keyword in normalized for keyword in MARKET_KEYWORDS)


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=MAX_QUERY_CHARS)
    session_id: str | None = None

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty")
        return cleaned

# Initialize Flask as 'application' for AWS EB
application = Flask(__name__)
CORS(application)


@application.route('/')
def health_check():
    return jsonify({"status": "active", "system": "Market Intelligence Swarm"})


@application.route('/research', methods=['POST'])
def run_research():
    """
    Old behavior: blocking request that returns only the final result.
    Keep this for non streaming clients.
    """
    payload_raw = request.get_json(silent=True) or {}
    try:
        payload = ResearchRequest(**payload_raw)
    except ValidationError as exc:
        return jsonify({"error": "Invalid request body", "details": exc.errors()}), 400

    query = payload.query
    session_id = payload.session_id or str(uuid.uuid4())

    guard_response = enforce_query_guards(query)
    if guard_response:
        return guard_response

    db_handler.log_query(session_id, query)

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "session_id": session_id
    }

    logger.info("Starting job %s :: %s", session_id, query)

    final_response = ""

    try:
        for event in market_graph.stream(initial_state):
            for key, value in event.items():
                if "messages" in value and value["messages"]:
                    msg = value["messages"][-1]
                    final_response = msg.content

        return jsonify({
            "session_id": session_id,
            "result": final_response
        })

    except Exception as e:
        logger.exception("Non-streaming research failed")
        return jsonify({"error": str(e)}), 500


@application.route('/research-stream', methods=['GET'])
def run_research_stream():
    """
    New behavior: streaming endpoint using Server Sent Events (SSE).
    The frontend will receive events as your LangGraph agents work.
    """
    query = (request.args.get('query') or "").strip()
    session_id = request.args.get('session_id', str(uuid.uuid4()))

    if not query:
        return jsonify({"error": "No query provided"}), 400

    if len(query) > MAX_QUERY_CHARS:
        return jsonify({"error": f"Query must be under {MAX_QUERY_CHARS} characters"}), 400

    guard_response = enforce_query_guards(query)
    if guard_response:
        return guard_response

    db_handler.log_query(session_id, query)

    logger.info("Starting streaming job %s :: %s", session_id, query)

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "session_id": session_id
    }

    def sse_format(payload: dict) -> str:
        # SSE protocol: "data: <json>\n\n"
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def event_stream():
        try:
            # Optional: let the client know we started
            yield sse_format({
                "type": "status",
                "session_id": session_id,
                "message": "Job started"
            })

            last_message = None

            for event in market_graph.stream(initial_state):
                # event is something like {"node_name": {"messages": [...], ...}}
                for node_name, state in event.items():
                    messages = state.get("messages", [])
                    if not messages:
                        continue

                    last_message = messages[-1]

                    payload = {
                        "type": "agent_message",
                        "session_id": session_id,
                        "node": node_name,
                        "message": last_message.content
                    }

                    # Send incremental update to the client
                    yield sse_format(payload)

            if last_message is not None:
                # Send final message marker
                yield sse_format({
                    "type": "final",
                    "session_id": session_id,
                    "message": last_message.content
                })

        except Exception as e:
            logger.exception("Streaming research failed for %s", session_id)
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": str(e)
            })

    response = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    # If you have nginx or a proxy that buffers, this can help
    response.headers["X-Accel-Buffering"] = "no"
    return response


if __name__ == "__main__":
    application.run(host="0.0.0.0", debug=True, port=5000, threaded=True)


def enforce_query_guards(query: str):
    if not is_market_intel_query(query):
        logger.info("Rejected non-market query: %s", query)
        return jsonify({"error": OUT_OF_SCOPE_MESSAGE}), 422

    if not passes_moderation(query):
        logger.info("Rejected query via moderation")
        return jsonify({"error": POLICY_VIOLATION_MESSAGE}), 422

    return None


def passes_moderation(query: str) -> bool:
    if moderation_client is None:
        return True
    try:
        response = moderation_client.moderations.create(
            model="omni-moderation-latest",
            input=query,
        )
        results = getattr(response, "results", [])
        if not results:
            return True
        return not results[0].flagged
    except Exception as exc:
        logger.warning("Moderation check failed: %s", exc)
        return True
