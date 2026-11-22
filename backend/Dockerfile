FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/src
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY migrations migrations
COPY src src
RUN useradd --system --uid 10001 --home /srv novacloud && mkdir -p /data/objects && chown -R novacloud /data
USER novacloud
EXPOSE 8000
CMD ["uvicorn", "--factory", "novacloud.api.app:app_factory", "--host", "0.0.0.0", "--port", "8000"]
