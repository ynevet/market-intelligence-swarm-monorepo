## System Overview

The Market Intelligence Swarm is a two-tier application:

1. **Backend (`server/`)** – a Flask API that orchestrates LangGraph agents, logs activity to MongoDB Atlas, and streams Server-Sent Events (SSE) to the UI.
2. **Frontend (`client/`)** – a React/Vite single-page app that triggers research runs, renders the live agent feed, and lets analysts export the final Markdown report.

Docker images exist for both services. `docker-compose.yml` wires them together for local work, while `deploy/Dockerrun.aws.json` feeds the same containers to AWS Elastic Beanstalk’s multi-container platform.

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

Each agent writes its latest message to MongoDB (`agent_logs`), enabling the UI and auditors to replay every step.

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
| `agent_logs` | `{ session_id, timestamp, agent, action, content }` – every intermediate step |
| `final_reports` | `{ session_id, timestamp, report }` – structured final answers |

Environment variables:

- `MONGO_URI` – connection string (SRV or standard)
- `OPENAI_API_KEY`, `TAVILY_API_KEY` – model/tool credentials

## Deployment Topology

- **Local**: `docker compose up --build` starts Flask on `5000` and Vite dev server on `5173`. The client talks to the backend through `VITE_SERVER_URL`.
- **AWS Elastic Beanstalk**:
  - Build images (`docker build -t mis-server ./server`, `docker build -t mis-client --target production ...`).
  - Push to Amazon ECR.
  - Update `deploy/Dockerrun.aws.json` with the image URIs and upload via `eb deploy`.
  - ALB forwards port 80 to the client container (`4173`). The client calls the API over the internal ECS network (`http://server:5000`).
  - Configure environment variables (`OPENAI_API_KEY`, `TAVILY_API_KEY`, `MONGO_URI`, `VITE_SERVER_URL`) within the EB console.

## Testing & Observability

- **Health check**: `GET /` returns `{ status: "active" }`.
- **Blocking run**: `POST /research`.
- **Streaming run**: `GET /research-stream?query=...` – SSE channel consumed by the UI.
- **Mongo logs**: Inspect Atlas collections to verify query ingestion and agent traces.
- **Frontend**: `npm run lint` ensures JSX/hooks correctness; download button exports Markdown evidence for manual QA.

