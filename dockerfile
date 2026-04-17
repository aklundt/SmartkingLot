FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system --no-cache \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --system --no-cache \
    $(grep -v "^opencv-python$" requirements.txt | tr '\n' ' ') \
    opencv-python-headless

COPY . .

ENV PYTHONUNBUFFERED=1
ENV YOLO_CONFIG_DIR=/app/.yolo
