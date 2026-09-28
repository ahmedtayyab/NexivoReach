# Render / production: frontend build + FastAPI on one port.
# Chromium is installed for contact-email JS fallback, but kept ephemeral
# (launch → one page → quit) so free/small instances do not hold a browser forever.
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist ./static
ENV PYTHONPATH=/app
ENV STATIC_DIR=/app/static
ENV CONTACT_BROWSER_ENABLED=true
ENV CONTACT_BROWSER_EPHEMERAL=true
ENV CONTACT_BROWSER_MAX_CONCURRENT=1
ENV HUNT_ENRICH_CONCURRENCY=2
RUN test -f /app/static/index.html
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
