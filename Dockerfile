FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .

RUN groupadd --system app \
    && useradd --system --gid app --create-home app \
    && mkdir -p /app/data/uploads /app/data/results \
    && chown -R app:app /app

COPY models/ ./models/
COPY config.json ./config.json

ENV GUITARCV_CONFIG_PATH=/app/config.json

USER app

EXPOSE 8000

CMD ["uvicorn", "guitarcv_restapi.main:app", "--host", "0.0.0.0", "--port", "4500"]