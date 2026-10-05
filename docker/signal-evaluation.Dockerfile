FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxrender1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.4.6 scipy==1.17.1 pydantic==2.13.5 psutil==7.2.2 httpx==0.28.1 matplotlib==3.11.2 eclipse-sumo==1.27.1 traci==1.27.1 sumolib==1.27.1
WORKDIR /study
ENV PYTHONPATH=/study/backend ATLAS_ROOT=/study PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "scripts/improve_signal_control.py"]
