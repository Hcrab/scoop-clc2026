FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY backend /app/backend
COPY frontend/dist /app/frontend/dist
COPY reports/evaluation.json /app/reports/evaluation.json
RUN useradd --uid 10001 --create-home scoop \
    && mkdir -p /app/data/cache /app/reports \
    && chown -R scoop:scoop /app/data /app/reports
USER scoop
EXPOSE 8008
CMD ["python", "-m", "uvicorn", "scoop.main:app", "--host", "0.0.0.0", "--port", "8008"]
