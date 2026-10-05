FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 ATLAS_DEVICE=cpu ATLAS_ROOT=/app ATLAS_DATA_DIR=/app/data OMP_NUM_THREADS=4
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir .
COPY docs ./docs
COPY artifacts ./artifacts
COPY scripts ./scripts
RUN mkdir -p data && useradd -u 10001 -m atlas && chown -R atlas:atlas /app
USER atlas
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "atlas.api:app", "--host", "0.0.0.0", "--port", "8000"]
