FROM node:24-bookworm-slim AS javascript
WORKDIR /app
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package.json
COPY backend/worker/package.json backend/worker/package.json
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend ./frontend
RUN npm run build
RUN npm prune --omit=dev --workspace hackathon-agent --include-workspace-root=false --ignore-scripts --no-audit --no-fund

FROM oven/bun:1.4.4 AS bun

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
RUN pip install --no-cache-dir fastapi==0.161.1 uvicorn==0.54.0 python-dotenv==1.2.4 pandas==3.1.0 httpx==0.28.1 boto3==1.43.118
COPY --from=javascript /app/node_modules ./node_modules
COPY --from=javascript /app/backend/worker ./backend/worker
COPY --from=javascript /app/frontend/dist ./frontend/dist
COPY backend ./backend
COPY data ./data
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp DEXTER_SOURCE_DIR=/app/vendor/dexter
RUN python backend/worker/setup.py
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "2"]
