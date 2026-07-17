FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY consumer ./consumer
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir --prefer-binary --extra-index-url https://download.pytorch.org/whl/cpu torch==2.13.0+cpu && \
    python -m pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV MIGRATIONS_DIR=/app/migrations

CMD ["consumer-run"]
