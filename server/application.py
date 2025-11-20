from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from langchain_core.messages import HumanMessage
from agents import market_graph
import uuid
from database import db_handler
import json

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
    data = request.json
    query = data.get('query')
    session_id = data.get('session_id', str(uuid.uuid4()))
    
    if not query:
        return jsonify({"error": "No query provided"}), 400

    db_handler.log_query(session_id, query)

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "session_id": session_id
    }

    print(f"--- Starting Job {session_id}: {query} ---")

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
        return jsonify({"error": str(e)}), 500


@application.route('/research-stream', methods=['GET'])
def run_research_stream():
    """
    New behavior: streaming endpoint using Server Sent Events (SSE).
    The frontend will receive events as your LangGraph agents work.
    """
    query = request.args.get('query')
    session_id = request.args.get('session_id', str(uuid.uuid4()))

    if not query:
        return jsonify({"error": "No query provided"}), 400

    db_handler.log_query(session_id, query)

    print(f"--- Starting Streaming Job {session_id}: {query} ---")

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
            # Send error over the stream
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
