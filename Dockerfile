FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8090

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libx11-6 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# Only copy app.py and owner_registry.py (main.py no longer exists)
COPY app.py owner_registry.py ./
COPY plate_best.pt vehicle_best.pt ./

RUN mkdir -p snapshots

EXPOSE 8090

CMD ["python", "app.py"]