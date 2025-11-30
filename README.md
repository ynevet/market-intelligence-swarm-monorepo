## Market Intelligence Swarm

Monorepo containing the LangGraph/Tavily-powered Flask backend (`server/`) and the Vite/React frontend (`client/`). Both services are containerized and orchestrated with Docker Compose for local development. See `docs/ARCHITECTURE.md` for an end-to-end design walkthrough (agents, LangGraph flow, Mongo schema, and system topology).

### Feature Highlights

- Multi-agent LangGraph with **Scout** (Tavily search/map/crawl) and **Analyst** (Tavily extract) workers, orchestrated by a Supervisor router.
- Tavily endpoints exercised: `search`, `map`, `crawl`, and `extract`.
- MongoDB Atlas logging of user prompts, intermediate agent messages, and final reports.
- React UI with live SSE log, markdown rendering, and an **Export Markdown** button for sharing.

### Prerequisites
- Docker Desktop 4.24+ (Compose v2)
- Node.js 20+ (only needed if you still want to run the client without Docker)
- Python 3.11+ (only needed if you still want to run the server without Docker)
- OpenAI, Tavily, and MongoDB credentials

### Environment Variables
Create a root `.env` file (ignored by git) with:
```
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=sk-...
MONGO_URI=mongodb+srv://...
VITE_SERVER_URL=http://server:5000

# Optional: LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=MIS-APP
```
`VITE_SERVER_URL` is optional locally but required when the frontend runs inside Docker so that it can reach the backend through the Docker network.

The LangChain variables enable [LangSmith](https://smith.langchain.com/) tracing for debugging and monitoring agent runs. They are optional but recommended for development.

For non-Docker workflows you can still drop a `.env` inside `server/` and `client/` as described in their READMEs.

### Local Development with Docker Compose
```
docker compose up --build
```
- `server` service runs `python application.py` for hot reloading (Flask dev server on port 5000).
- `client` service runs `npm run dev -- --host 0.0.0.0 --port 5173`.
- Access the UI at `http://localhost:5173`. The UI talks to the backend at `http://localhost:5000`.
- Stop with `Ctrl+C` (or `docker compose down` to clean up containers).



