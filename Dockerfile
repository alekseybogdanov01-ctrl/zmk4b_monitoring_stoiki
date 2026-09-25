# Backend + ML: FastAPI и инференс YOLO.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics

# libglib/libgomp нужны cv2 и torch даже в headless-сборке
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Отдельные слои: зависимости переустанавливаются только при смене requirements.
# torch берём из CPU-индекса — иначе тянутся пакеты CUDA на несколько гигабайт.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

# Что не попадает в образ — см. .dockerignore (веса, датасеты, node_modules).
COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
