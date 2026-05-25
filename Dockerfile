FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8090

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py mobile_server.py dashboard.py owner_registry.py ./
COPY vehicle_best.pt plate_best.pt ./

RUN mkdir -p snapshots

EXPOSE 8090

CMD ["python", "mobile_server.py", "--host", "0.0.0.0"]
