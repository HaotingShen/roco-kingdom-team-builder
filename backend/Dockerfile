FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for psycopg2 and general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy entire project (needed because backend imports use "backend." prefix)
COPY backend/ backend/

# Expose port
EXPOSE 8000

# Run FastAPI - bind to 0.0.0.0 inside container (Docker networking isolates it)
# docker-compose.prod.yml maps this to 127.0.0.1:8000 on the host
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]