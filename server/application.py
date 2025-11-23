import datetime
import json
import logging
import os
import re
import time
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


def is_market_intel_query(query: str) -> tuple[bool, dict]:
    """Check if query is market intel related using LLM. Returns (is_valid, classification_metadata)"""
    if classifier_llm is None:
        return True, {"classification_skipped": True}  # skip check if no API key
    
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
        metadata = {
            "classification_skipped": False,
            "is_market_intel": result.is_market_intel,
            "confidence": result.confidence,
            "classification_reason": result.reason
        }
        return is_valid, metadata
    except Exception as e:
        logger.warning("Classification failed: %s", e)
        return True, {"classification_skipped": True, "classification_error": str(e)}  # allow through on error


def validate_query_guards(query: str) -> tuple[str | None, dict]:
    """Check query against guardrails, return (error_msg or None, metadata)"""
    is_valid, classification_meta = is_market_intel_query(query)
    if not is_valid:
        logger.info("Rejected: %s", query[:50])
        return OUT_OF_SCOPE_MESSAGE, classification_meta

    moderation_passed = passes_moderation(query)
    if not moderation_passed:
        logger.info("Rejected by moderation")
        return POLICY_VIOLATION_MESSAGE, {**classification_meta, "moderation_passed": False}

    return None, {**classification_meta, "moderation_passed": True}


def enforce_query_guards(query: str):
    """For non-streaming endpoints"""
    error_msg, _ = validate_query_guards(query)
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


def extract_urls_from_content(content: str) -> list[str]:
    """Extract URLs from agent message content"""
    # Simple regex to find URLs
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, content)
    # Remove trailing punctuation
    urls = [url.rstrip('.,;:!?)') for url in urls]
    return list(set(urls))  # deduplicate


def extract_request_metadata(request) -> dict:
    """Extract basic request metadata for logging (IP only, no user identification)"""
    metadata = {}
    
    # Extract IP address (handles proxies) - for security/analytics only
    if request.headers.get('X-Forwarded-For'):
        metadata['ip_address'] = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        metadata['ip_address'] = request.headers.get('X-Real-IP')
    else:
        metadata['ip_address'] = request.remote_addr or 'unknown'
    
    return metadata


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=MAX_QUERY_CHARS)

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
    session_id = str(uuid.uuid4())

    guard_response = enforce_query_guards(query)
    if guard_response:
        return guard_response

    # Extract basic request metadata for logging (IP only)
    request_metadata = extract_request_metadata(request)

    # Get query metadata
    _, query_metadata = validate_query_guards(query)
    
    db_handler.log_query(session_id, query, request_metadata)

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "session_id": session_id
    }

    logger.info("Starting job %s :: %s", session_id, query)
    
    start_time = time.time()
    final_response = ""
    node_counts = {"Supervisor": 0, "Scout": 0, "Analyst": 0}
    discovered_urls = set()
    status = "success"
    error_message = None

    try:
        for event in market_graph.stream(initial_state, config={"recursion_limit": RECURSION_LIMIT}):
            for node_name, value in event.items():
                if node_name in node_counts:
                    node_counts[node_name] += 1
                if "messages" in value and value["messages"]:
                    msg = value["messages"][-1]
                    final_response = msg.content
                    # Extract URLs from messages
                    urls = extract_urls_from_content(msg.content)
                    discovered_urls.update(urls)

        duration = time.time() - start_time

        # Log final report to MongoDB with metadata
        if final_response:
            metadata = {
                "query": query,
                "start_time": datetime.datetime.utcfromtimestamp(start_time),
                "duration_seconds": round(duration, 2),
                "status": status,
                "node_execution_counts": node_counts,
                "total_steps": sum(node_counts.values()),
                "discovered_urls": list(discovered_urls),
                "url_count": len(discovered_urls),
                **query_metadata
            }
            db_handler.log_final_report(session_id, {"content": final_response}, metadata)

        return jsonify({
            "session_id": session_id,
            "result": final_response
        })

    except GraphRecursionError as exc:
        duration = time.time() - start_time
        status = "recursion_limit"
        error_message = str(exc)
        logger.warning("Recursion limit (%s) hit for session %s: %s", RECURSION_LIMIT, session_id, exc)
        
        # Log failed attempt with metadata
        metadata = {
            "query": query,
            "start_time": datetime.datetime.utcfromtimestamp(start_time),
            "duration_seconds": round(duration, 2),
            "status": status,
            "error_message": error_message,
            "node_execution_counts": node_counts,
            "total_steps": sum(node_counts.values()),
            "discovered_urls": list(discovered_urls),
            **query_metadata
        }
        db_handler.log_final_report(session_id, {"content": "", "error": RECURSION_MESSAGE}, metadata)
        
        return jsonify({"error": RECURSION_MESSAGE}), 429
    except Exception as e:
        duration = time.time() - start_time
        status = "error"
        error_message = str(e)
        logger.exception("Non-streaming research failed")
        
        # Log failed attempt with metadata
        metadata = {
            "query": query,
            "start_time": datetime.datetime.utcfromtimestamp(start_time),
            "duration_seconds": round(duration, 2),
            "status": status,
            "error_message": error_message,
            "node_execution_counts": node_counts,
            "total_steps": sum(node_counts.values()),
            "discovered_urls": list(discovered_urls),
            **query_metadata
        }
        db_handler.log_final_report(session_id, {"content": "", "error": "Something went wrong while running this query."}, metadata)
        
        return jsonify({"error": "Something went wrong while running this query."}), 500


@application.route('/research-stream', methods=['GET'])
def run_research_stream():
    """SSE streaming endpoint"""
    query = (request.args.get('query') or "").strip()
    session_id = str(uuid.uuid4())

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
        guard_error, query_metadata = validate_query_guards(query)
        if guard_error:
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": guard_error
            })
            return

        # Extract basic request metadata for logging (IP only)
        request_metadata = extract_request_metadata(request)

        db_handler.log_query(session_id, query, request_metadata)
        logger.info("Starting job %s", session_id)

        initial_state = {
            "messages": [HumanMessage(content=query)],
            "session_id": session_id
        }

        start_time = time.time()
        node_counts = {"Supervisor": 0, "Scout": 0, "Analyst": 0}
        discovered_urls = set()
        status = "success"
        error_message = None

        try:
            yield sse_format({
                "type": "status",
                "session_id": session_id,
                "message": "Job started"
            })

            last_message = None

            for event in market_graph.stream(initial_state, config={"recursion_limit": RECURSION_LIMIT}):
                for node_name, state in event.items():
                    if node_name in node_counts:
                        node_counts[node_name] += 1
                    
                    messages = state.get("messages", [])
                    if messages:
                        last_message = messages[-1]
                        # Extract URLs from messages
                        urls = extract_urls_from_content(last_message.content)
                        discovered_urls.update(urls)
                        
                        yield sse_format({
                            "type": "agent_message",
                            "session_id": session_id,
                            "node": node_name,
                            "message": last_message.content
                        })
                    elif node_name in node_counts:
                        # Log node execution even if no messages (for debugging)
                        logger.debug(f"Node {node_name} executed but no messages in state")

            duration = time.time() - start_time

            if last_message is not None:
                # Log final report to MongoDB with metadata
                metadata = {
                    "query": query,
                    "start_time": datetime.datetime.utcfromtimestamp(start_time),
                    "duration_seconds": round(duration, 2),
                    "status": status,
                    "node_execution_counts": node_counts,
                    "total_steps": sum(node_counts.values()),
                    "discovered_urls": list(discovered_urls),
                    "url_count": len(discovered_urls),
                    **query_metadata
                }
                db_handler.log_final_report(session_id, {"content": last_message.content}, metadata)
                
                yield sse_format({
                    "type": "final",
                    "session_id": session_id,
                    "message": last_message.content
                })

        except GraphRecursionError as exc:
            duration = time.time() - start_time
            status = "recursion_limit"
            error_message = str(exc)
            logger.warning("Recursion limit (%s) hit for session %s: %s", RECURSION_LIMIT, session_id, exc)
            
            # Log failed attempt with metadata
            metadata = {
                "query": query,
                "start_time": datetime.datetime.utcfromtimestamp(start_time),
                "duration_seconds": round(duration, 2),
                "status": status,
                "error_message": error_message,
                "node_execution_counts": node_counts,
                "total_steps": sum(node_counts.values()),
                "discovered_urls": list(discovered_urls),
                **query_metadata
            }
            db_handler.log_final_report(session_id, {"content": "", "error": RECURSION_MESSAGE}, metadata)
            
            yield sse_format({
                "type": "error",
                "session_id": session_id,
                "message": RECURSION_MESSAGE
            })
        except Exception as e:
            duration = time.time() - start_time
            status = "error"
            error_message = str(e)
            logger.exception("Streaming research failed for %s", session_id)
            
            # Log failed attempt with metadata
            metadata = {
                "query": query,
                "start_time": datetime.datetime.utcfromtimestamp(start_time),
                "duration_seconds": round(duration, 2),
                "status": status,
                "error_message": error_message,
                "node_execution_counts": node_counts,
                "total_steps": sum(node_counts.values()),
                "discovered_urls": list(discovered_urls),
                **query_metadata
            }
            db_handler.log_final_report(session_id, {"content": "", "error": "Something went wrong while running this query."}, metadata)
            
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
