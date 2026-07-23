# Deployment Guide

## Local Development

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
Copy-Item .env.example .env
# Edit .env with your Azure credentials

# 3. Run (auto-reload enabled in development)
python run.py

# 4. Open browser
start http://localhost:8000
```

---

## Production (Windows / Linux)

### Environment variables checklist

```env
APP_ENV=production
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=<secret>
AZURE_OPENAI_REALTIME_DEPLOYMENT=gpt-4o-realtime-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_PATH=/data/sainsburys.db
CORS_ORIGINS=https://your-domain.com
```

### Run with Gunicorn + Uvicorn workers (Linux)

```bash
pip install gunicorn
gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 2 \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --keepalive 75
```

> Use 2 workers for WebSocket-heavy workloads; SQLite handles concurrent reads well with WAL mode.

---

## Docker

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

ENV DATABASE_PATH=/data/sainsburys.db
ENV APP_ENV=production
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000

EXPOSE 8000

CMD ["python", "run.py", "--env", "production"]
```

### Build & run

```bash
docker build -t sainsburys-voice-agent .

docker run -d \
  --name voice-agent \
  -p 8000:8000 \
  -v sainsburys-data:/data \
  -e AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" \
  -e AZURE_OPENAI_API_KEY="your-key" \
  -e AZURE_OPENAI_REALTIME_DEPLOYMENT="gpt-4o-realtime-preview" \
  -e AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o" \
  sainsburys-voice-agent
```

---

## Azure Container Apps

```bash
# Create resource group
az group create --name sainsburys-rg --location uksouth

# Create Container Apps environment
az containerapp env create \
  --name sainsburys-env \
  --resource-group sainsburys-rg \
  --location uksouth

# Deploy
az containerapp create \
  --name sainsburys-voice-agent \
  --resource-group sainsburys-rg \
  --environment sainsburys-env \
  --image your-registry/sainsburys-voice-agent:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --secrets \
    azure-openai-key="your-key" \
  --env-vars \
    AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" \
    AZURE_OPENAI_API_KEY=secretref:azure-openai-key \
    AZURE_OPENAI_REALTIME_DEPLOYMENT="gpt-4o-realtime-preview" \
    APP_ENV=production
```

> **Note:** Azure Container Apps supports WebSocket connections with sticky sessions automatically.

---

## Nginx Reverse Proxy (HTTPS)

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    # WebSocket support
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Health Monitoring

```bash
# Basic health check
curl https://your-domain.com/health

# Watch active sessions
watch -n 5 'curl -s https://your-domain.com/api/v1/sessions | python -m json.tool'
```

---

## Scaling Considerations

| Concern | Recommendation |
|---------|---------------|
| SQLite under load | Suitable for up to ~50 concurrent sessions; migrate to PostgreSQL for more |
| WebSocket concurrency | Each session holds 2 WS connections (browser + Azure Realtime) |
| Azure quota | Check TPM (tokens per minute) quota on your Azure OpenAI deployment |
| Audio latency | Run server geographically close to your Azure OpenAI resource region |
| HTTPS | Required for browser microphone access (`getUserMedia`) |

---

## Security Checklist

- [ ] `.env` file is gitignored
- [ ] `CORS_ORIGINS` is set to your domain (not `*`) in production
- [ ] `APP_ENV=production` disables Swagger UI (`/docs`)
- [ ] Azure OpenAI endpoint uses HTTPS
- [ ] Database file is on a persistent volume (not container ephemeral storage)
- [ ] API key is stored in a secrets manager (Azure Key Vault) rather than env var in production
