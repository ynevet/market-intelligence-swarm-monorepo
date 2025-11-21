import json
import logging
import os
import uuid

from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
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
RECURSION_LIMIT = int(os.environ.get('GRAPH_RECURSION_LIMIT', '200'))
RECURSION_MESSAGE = (
    "We're still working through that request. Please try again with a bit more detail."
)
POLICY_VIOLATION_MESSAGE = (
    "This request can't be processed because it violates our usage guidelines. "
    "Try rephrasing with a professional market or competitive research question."
)
moderation_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) if os.environ.get("OPENAI_API_KEY") else None

# LLM for checking if queries are market-intel related
classifier_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0) if os.environ.get("OPENAI_API_KEY") else None

OUT_OF_SCOPE_MESSAGE = (
    "Thanks for your request! This assistant focuses on market and competitive "
    "research tasks (pricing, positioning, competitor insights, etc.). "
    "Please submit a market intelligence query so I can help."
)


class QueryClassification(BaseModel):
    is_market_intel: bool = Field(description="True if query is about market research, competitive analysis, pricing, etc")
    confidence: float = Field(description="Confidence 0-1", ge=0.0, le=1.0)
    reason: str = Field(description="Why this classification")


def is_market_intel_query(query: str) -> bool:
    """Check if query is market intel related using LLM"""
    if classifier_llm is None:
        return True  # skip check if no API key
    
    try:
        prompt = f"""Classify whether this user query is about market intelligence, competitive research, or business analysis.

Market intelligence queries include:
- Competitive analysis and benchmarking
- Pricing research and strategy
- Market positioning and differentiation
- Product comparisons
- Go-to-market (GTM) research
- Industry trends and insights
- Sales strategy research
- Market sizing and opportunity analysis

Query: "{query}"

Respond with whether this is a market intelligence query and your confidence level."""

        result = classifier_llm.with_structured_output(QueryClassification).invoke(prompt)
        is_valid = result.is_market_intel and result.confidence >= 0.7
        logger.info("Query classification: valid=%s, conf=%.2f", is_valid, result.confidence)
        return is_valid
    except Exception as e:
        logger.warning("Classification failed: %s", e)
        return True  # allow through on error


def validate_query_guards(query: str) -> str | None:
    """Check query against guardrails, return error msg or None"""
    if not is_market_intel_query(query):
        logger.info("Rejected: %s", query[:50])
        return OUT_OF_SCOPE_MESSAGE

    if not passes_moderation(query):
        logger.info("Rejected by moderation")
        return POLICY_VIOLATION_MESSAGE

    return None


def enforce_query_guards(query: str):
    """For non-streaming endpoints"""
    error_msg = validate_query_guards(query)
    if error_msg:
        return jsonify({"error": error_msg}), 422
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
    """Blocking endpoint for non-streaming clients"""
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
        for event in market_graph.stream(initial_state, config={"recursion_limit": RECURSION_LIMIT}):
            for key, value in event.items():
                if "messages" in value and value["messages"]:
                    msg = value["messages"][-1]
                    final_response = msg.content

        return jsonify({
            "session_id": session_id,
            "result": final_response
        })

    except GraphRecursionError as exc:
        logger.warning("Recursion limit (%s) hit for session %s: %s", RECURSION_LIMIT, session_id, exc)
        return jsonify({"error": RECURSION_MESSAGE}), 429
    except Exception as e:
        logger.exception("Non-streaming research failed")
        return jsonify({"error": "Something went wrong while running this query."}), 500


@application.route('/research-stream', methods=['GET'])
def run_research_stream():
    """SSE streaming endpoint"""
    query = (request.args.get('query') or "").strip()
    session_id = request.args.get('session_id', str(uuid.uuid4()))

    def sse_format(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def event_stream():
        # Validate basic query requirements
        if not query:
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": "No query provided"
            })
            return

        if len(query) > MAX_QUERY_CHARS:
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": f"Query must be under {MAX_QUERY_CHARS} characters"
            })
            return

        # Validate guardrails and send error through SSE if rejected
        guard_error = validate_query_guards(query)
        if guard_error:
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": guard_error
            })
            return

        db_handler.log_query(session_id, query)
        logger.info("Starting job %s", session_id)

        initial_state = {
            "messages": [HumanMessage(content=query)],
            "session_id": session_id
        }

        try:
            yield sse_format({
                "type": "status",
                "session_id": session_id,
                "message": "Job started"
            })

            last_message = None

            for event in market_graph.stream(initial_state, config={"recursion_limit": RECURSION_LIMIT}):
                for node_name, state in event.items():
                    messages = state.get("messages", [])
                    if not messages:
                        continue

                    last_message = messages[-1]
                    yield sse_format({
                        "type": "agent_message",
                        "session_id": session_id,
                        "node": node_name,
                        "message": last_message.content
                    })

            if last_message is not None:
                yield sse_format({
                    "type": "final",
                    "session_id": session_id,
                    "message": last_message.content
                })

        except GraphRecursionError as exc:
            logger.warning("Recursion limit (%s) hit for session %s: %s", RECURSION_LIMIT, session_id, exc)
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": RECURSION_MESSAGE
            })
        except Exception as e:
            logger.exception("Streaming research failed for %s", session_id)
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": "Something went wrong while running this query."
            })

    response = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


if __name__ == "__main__":
    application.run(host="0.0.0.0", debug=True, port=5000, threaded=True)
