## System Overview

The Market Intelligence Swarm is a two-tier application:

1. **Backend (`server/`)** – a Flask API that orchestrates LangGraph agents, logs activity to MongoDB Atlas, and streams Server-Sent Events (SSE) to the UI.
2. **Frontend (`client/`)** – a React/Vite single-page app that triggers research runs, renders the live agent feed, and lets analysts export the final Markdown report.

Docker images exist for both services. `docker-compose.yml` wires them together for local work.

## Agent Architecture

```
           ┌──────────┐
           │Supervisor│
           └────┬─────┘
                │
   ┌────────────┴────────────┐
   │                         │
┌───────┐               ┌────────┐
│ Scout │               │Analyst │
└──┬────┘               └────┬───┘
   │                         │
   │ Tavily search/map/crawl │ Tavily extract
   │                         │
   └─────────► Mongo Logs ◄──┘
```

- **Scout** (`create_react_agent`): Combines `tavily_search_research`, `tavily_map_site`, and `tavily_crawl_summary` to chart relevant sources.
- **Analyst**: Applies `tavily_extract_content` to pull structured evidence from Scout-proposed URLs.
- **Supervisor**: A router agent that decides the next worker (`Scout`, `Analyst`, or `FINISH`) using a structured output policy.

Each agent writes its latest message to MongoDB (`agent_logs`), enabling the UI and auditors to replay every step. Upon completion, the final report is persisted to `final_reports` with comprehensive execution metadata including timing, node execution counts, discovered URLs, and query classification results.

## LangGraph Flow

1. **START → Supervisor** – seeds the graph with the user prompt.
2. **Supervisor → Scout/Analyst** – dynamic hop based on current context (`next` field in `AgentState`).
3. **Workers → Supervisor** – after each invocation, LangGraph returns control to the Supervisor with appended messages.
4. **Supervisor → END** – when `FINISH` is emitted, the graph finalizes and the SSE endpoint emits the final payload.

This pattern satisfies the assignment’s “multi-agent architecture with clear roles” clause and keeps each toolchain independent.

## Data Model

MongoDB Atlas (`market_swarm_db`) stores:

| Collection | Shape |
|------------|-------|
| `agent_logs` | `{ session_id, timestamp, agent, action, content, ip_address? }` – every intermediate step, with optional IP for request tracking |
| `final_reports` | `{ session_id, timestamp, report, query, start_time, duration_seconds, status, node_execution_counts, total_steps, discovered_urls, url_count, is_market_intel?, confidence?, moderation_passed?, error_message? }` – structured final answers with comprehensive execution metadata |

Environment variables:

- `MONGO_URI` – connection string (SRV or standard)
- `OPENAI_API_KEY`, `TAVILY_API_KEY` – model/tool credentials

## Testing & Observability

- **Health check**: `GET /` returns `{ status: "active" }`.
- **Blocking run**: `POST /research`.
- **Streaming run**: `GET /research-stream?query=...` – SSE channel consumed by the UI.
- **Mongo logs**: Inspect Atlas collections to verify query ingestion and agent traces. The `final_reports` collection includes execution metrics, discovered sources, and query classification metadata for analytics and debugging.
- **Frontend**: `npm run lint` ensures JSX/hooks correctness; download button exports Markdown evidence for manual QA.

