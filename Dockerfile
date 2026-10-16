FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home heimdall
COPY --chown=heimdall:heimdall run.py ./
COPY --chown=heimdall:heimdall src ./src
COPY --chown=heimdall:heimdall scripts/healthcheck.py ./scripts/healthcheck.py
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD ["python", "scripts/healthcheck.py"]
CMD ["python", "run.py"]
