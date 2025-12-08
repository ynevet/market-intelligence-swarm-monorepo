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
- `server` service runs Gunicorn with threading support (port 5000) for reliable long-running SSE streaming.
- `client` service runs `npm run dev -- --host 0.0.0.0 --port 5173`.
- Access the UI at `http://localhost:5173`. The UI talks to the backend at `http://localhost:5000`.
- Stop with `Ctrl+C` (or `docker compose down` to clean up containers).

#### Watch Mode (Hot Reload)
For automatic rebuilds and restarts when source code changes:
```
docker compose watch
```
- **Server**: Automatically rebuilds and restarts when Python files (`.py`) or `requirements.txt` change
- **Client**: Syncs `src/` and `public/` folders instantly with Vite's HMR, rebuilds when `package.json` changes

### Deployment

The project uses **GitHub Actions** for automated deployment to **AWS Elastic Beanstalk** when code is merged to the `main` branch.

#### Deployment Architecture

- **Server**: Deployed to `mis-app-api-dev` environment (EB application: `mis-app-api`)
- **Client**: Deployed to `mis-app-ui-dev` environment (EB application: `mis-app-ui`)
- Both services use Docker containers on Amazon Linux 2023

#### Automatic Deployment Workflow

The deployment workflow (`.github/workflows/deploy.yml`) automatically:

1. **Detects Changes**: Only triggers when source code files or Dockerfiles change:
   - Server: `server/**/*.py`, `server/requirements.txt`, `server/Dockerfile`
   - Client: `client/src/**`, `client/public/**`, `client/Dockerfile`, `client/package.json`, `client/package-lock.json`

2. **Smart Deployment**: Only deploys the service(s) that actually changed:
   - If only server files change → deploys server only
   - If only client files change → deploys client only
   - If both change → deploys both

3. **Deployment Process**:
   - Pulls EB configuration using `eb init` (creates config files on-the-fly)
   - Deploys using `eb deploy` to the respective environments
   - Config files are created temporarily during CI/CD and not committed to git

#### Setup Requirements

1. **GitHub Secrets**: Add the following secrets in your GitHub repository (Settings → Secrets and variables → Actions):
   - `AWS_ACCESS_KEY_ID`: Your AWS access key ID
   - `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key

2. **AWS Elastic Beanstalk**: Ensure your AWS account has:
   - EB applications `mis-app-api` and `mis-app-ui` already created
   - Environments `mis-app-api-dev` and `mis-app-ui-dev` configured
   - Proper IAM permissions for the AWS credentials to deploy to EB

3. **EB Configuration**: The workflow uses EB CLI to pull existing configuration from AWS, so your EB environments should already be set up with:
   - Platform: Docker running on 64bit Amazon Linux 2023
   - Region: us-east-1

#### Manual Deployment

If you need to deploy manually:

```bash
# Server
cd server
eb init mis-app-api --region us-east-1 --platform "Docker running on 64bit Amazon Linux 2023"
eb deploy mis-app-api-dev

# Client
cd client
eb init mis-app-ui --region us-east-1 --platform "Docker running on 64bit Amazon Linux 2023"
eb deploy mis-app-ui-dev
```

#### Monitoring Deployments

- Check GitHub Actions tab to see deployment status and logs
- Monitor EB environments in AWS Console for deployment progress
- View application logs in EB console or via `eb logs` command



