FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/src \
    OPSAGENT_HOST=0.0.0.0 \
    OPSAGENT_PORT=80
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1/health')"
CMD ["python", "-m", "opsagent", "prototype"]
