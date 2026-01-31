FROM python:3.11-alpine

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Run as non-root user
RUN adduser -D -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

CMD ["python", "-u", "-m", "src.sync"]
