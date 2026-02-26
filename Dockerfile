FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY api/ ./api/

# Make both src/ and api/ importable without package prefixes
ENV PYTHONPATH=/app/src:/app/api

EXPOSE 8000

CMD PYTHONPATH=/app/src:/app/api uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
