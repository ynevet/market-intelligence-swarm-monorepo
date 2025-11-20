## Market Intelligence Swarm

Monorepo containing the LangGraph/Tavily-powered Flask backend (`server/`) and the Vite/React frontend (`client/`). Both services are containerized and orchestrated with Docker Compose for local development, and the Dockerfiles are production-ready for AWS Elastic Beanstalk multi-container deployments.

### Prerequisites
- Docker Desktop 4.24+ (Compose v2)
- Node.js 20+ (only needed if you still want to run the client without Docker)
- Python 3.11+ (only needed if you still want to run the server without Docker)
- Tavily and MongoDB credentials

### Environment Variables
Create a root `.env` file (ignored by git) with:
```
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=sk-...
MONGO_URI=mongodb+srv://...
VITE_SERVER_URL=http://server:5000
```
`VITE_SERVER_URL` is optional locally but required when the frontend runs inside Docker or in the cloud so that it can reach the backend through the Docker network or load balancer.

For non-Docker workflows you can still drop a `.env` inside `server/` and `client/` as described in their READMEs.

### Local Development with Docker Compose
```
docker compose up --build
```
- `server` service runs `python application.py` for hot reloading (Flask dev server on port 5000).
- `client` service runs `npm run dev -- --host 0.0.0.0 --port 5173`.
- Access the UI at `http://localhost:5173`. The UI talks to the backend at `http://localhost:5000`.
- Stop with `Ctrl+C` (or `docker compose down` to clean up containers).

### Production-Grade Images
The Dockerfiles include production entrypoints:
- Backend uses Gunicorn (`gthread` workers) to keep Server-Sent Events responsive.
- Frontend has a multi-stage build that compiles Vite assets and serves them via `serve`.

Build the hardened images locally:
```
docker build -t mis-server ./server
docker build -t mis-client --target production --build-arg VITE_SERVER_URL=https://your-api-url ./client
```

### AWS Elastic Beanstalk Deployment Notes
1. Use the **Multi-container Docker on Amazon Linux 2** platform so Elastic Beanstalk spins up an ECS cluster that understands multiple containers.
2. Push both images to Amazon ECR (one repository per service). Tag them `latest` or any semantic version.
3. Create a `Dockerrun.aws.json` (v2) that references the two ECR images. Example:
```
{
  "AWSEBDockerrunVersion": 2,
  "containerDefinitions": [
    {
      "name": "server",
      "image": "ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/mis-server:latest",
      "essential": true,
      "memory": 512,
      "portMappings": [{ "containerPort": 5000 }],
      "environment": [
        { "name": "OPENAI_API_KEY", "value": "****" },
        { "name": "TAVILY_API_KEY", "value": "****" },
        { "name": "MONGO_URI", "value": "****" }
      ]
    },
    {
      "name": "client",
      "image": "ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/mis-client:latest",
      "essential": true,
      "memory": 256,
      "portMappings": [{ "containerPort": 4173 }],
      "links": ["server"],
      "environment": [
        { "name": "NODE_ENV", "value": "production" },
        { "name": "VITE_SERVER_URL", "value": "http://server:5000" }
      ]
    }
  ]
}
```
4. Zip `Dockerrun.aws.json` (and any `.ebextensions` you might add later) and deploy with `eb deploy`.
5. In the EB console, configure health checks and listener rules so that:
   - Port 80 (ALB listener) points to the `client` container (`4173`).
   - Optional: add path-based rule `/api/*` → `server:5000` if you expose the API directly. Alternatively, keep the server private and let the client call it via the ECS internal network (`http://server:5000` as configured above).
6. Store secrets (Tavily, MongoDB) as EB environment variables; they override the defaults from `Dockerrun`.

With this setup you can iterate locally with `docker compose` and later promote the same containers to AWS Elastic Beanstalk without code changes.

