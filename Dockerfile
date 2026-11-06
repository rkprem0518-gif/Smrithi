FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEMO_MODE=1 \
    HOST=0.0.0.0

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY config ./config
COPY prompts ./prompts
COPY fixtures ./fixtures
COPY scripts ./scripts

# Run as an unprivileged user; the SQLite file lives in /app/data (mount a volume there to persist).
RUN useradd --create-home smriti && mkdir -p /app/data && chown -R smriti /app/data
USER smriti
ENV DATABASE_URL=sqlite:////app/data/smriti.db

# The three apps: family :8000, elder :8001, care team :8002 (one process, live-synced).
EXPOSE 8000 8001 8002
CMD ["python", "scripts/run_demo.py"]
