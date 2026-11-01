FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt ./requirements.txt
# Use the official CPU-only wheels. The local, model-tested dependency pair is
# torch 2.14.1 / torchvision 0.29.1; install it before Ultralytics so pip does
# not resolve a CUDA-enabled PyTorch build in this CPU service.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu \
      torch==2.14.1 torchvision==0.29.1 && \
    pip install -r requirements.txt

COPY backend/app ./app
COPY backend/ai_service ./ai_service

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
