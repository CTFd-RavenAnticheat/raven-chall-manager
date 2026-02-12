FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy and install chall-manager SDK
COPY ../sdk/python /tmp/chall-manager-sdk
RUN pip install -e /tmp/chall-manager-sdk

# Create non-root user
RUN useradd -m -u 1000 challmanager && chown -R challmanager:challmanager /app
USER challmanager

# Expose port
EXPOSE 5000

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:app"]