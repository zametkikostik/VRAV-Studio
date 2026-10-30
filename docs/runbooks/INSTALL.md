# VRAV Studio — Install

## Development

### Prerequisites
- Python 3.12+
- Node 20+
- Docker (Postgres + Redis)
- Optional: ffmpeg/ffprobe on PATH

### API
```bash
cp .env.example .env
docker compose -f infra/docker/docker-compose.dev.yml up -d
cd apps/api
pip install -r requirements.txt
export PYTHONPATH=".:../../packages/ai-gateway"
alembic -c alembic.ini upgrade head
uvicorn app.main:app --reload --port 8000
```

### Web UI
```bash
cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

### Desktop
```bash
cd apps/web && npm run dev
cd apps/desktop && npm install && npm run dev
```
