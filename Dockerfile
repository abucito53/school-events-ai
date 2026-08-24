FROM python:3.12-slim

# Ohne das puffert Python print()-Ausgaben, solange kein Terminal angehängt
# ist (wie in einem Container) - Log-Zeilen würden dann erst mit grosser
# Verzögerung (oder gar nicht) bei "docker compose logs" bzw. in Docker
# Desktop ankommen.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schultermine ./schultermine

CMD ["python3", "-m", "schultermine", "scheduler"]
