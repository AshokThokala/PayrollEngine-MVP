FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Several worker processes per container (WEB_CONCURRENCY, default 2). The API is stateless:
# logins are signed tokens, so any worker or container can serve any request.
# SECRET_KEY must be the same for all of them.
ENV WEB_CONCURRENCY=2
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*'"]
