FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY detector ./detector
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV MIGRATIONS_DIR=/app/migrations

CMD ["detector-run"]
