# NepseTerminal Crew API

## Setup

```sh
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## API
- `GET /health`
- `POST /api/v1/agents`
- `GET /api/v1/agents`
- `PATCH /api/v1/agents/{agent_id}`
- `POST /api/v1/runs/agent`
- `POST /api/v1/runs/crew`
- `GET /api/v1/runs`
- `GET /api/v1/scrape?url=...`
