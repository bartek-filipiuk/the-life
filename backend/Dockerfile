FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim

# Security: non-root user
RUN groupadd -r thelife && useradd -r -g thelife -d /app thelife

WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ app/
COPY config.yaml .

# Create data directory
RUN mkdir -p /app/data && chown -R thelife:thelife /app

USER thelife

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
