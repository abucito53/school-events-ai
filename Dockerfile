FROM python:3.12-slim

# Without this, Python buffers print()/log output whenever no terminal is
# attached (as in a container) - log lines would then show up with a big
# delay (or not at all) in "docker compose logs" / Docker Desktop.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY school_events ./school_events

CMD ["python3", "-m", "school_events", "scheduler"]
