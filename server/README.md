## Market Intelligence Swarm Backend

This directory contains the Flask-based Market Intelligence backend, exposing APIs that orchestrate AI agents for market analysis via LangGraph workflows and the Tavily API. The app loads environment variables via `python-dotenv`, so placing a `.env` file in `server/` keeps secrets out of git.

### Environment Variables
- `OPENAI_API_KEY` (required): used by LangGraph agents via `langchain-openai`.
- `TAVILY_API_KEY` (required): lets the Tavily tools crawl and extract site content.
- `MONGO_URI` (optional but recommended): enables query, step, and report logging inside MongoDB Atlas. When missing, data persistence is disabled.

You can declare them inside `server/.env`, for example:
```
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=sk-...
MONGO_URI=mongodb+srv://...
```

### Virtual Environment
Create a project-scoped virtual environment inside `server/`:
```
python -m venv server\.venv
```

Activate it before installing dependencies:
- Windows PowerShell:
  ```
  server\.venv\Scripts\Activate.ps1
  ```
- macOS/Linux:
  ```
  source server/.venv/bin/activate
  ```

Install requirements from this directory:
```
pip install -r server/requirements.txt
```

When you are done working, deactivate the environment with:
```
deactivate
```

### Run the Application
From the repo root (with the virtualenv active):
```
python server/application.py
```
This starts Flask on `http://127.0.0.1:5000`.

### Quick Test
Use the streaming endpoint example:
```
curl --location \
  'http://127.0.0.1:5000/research-stream?query=Map%20the%20website%20structure%20of%20Tavily%20and%20extract%20their%20pricing%20tiers.'
```

