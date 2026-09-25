FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m pip install --no-cache-dir .

RUN mkdir -p /state && chown app:app /state

USER 10001:10001

ENTRYPOINT ["python", "-m", "app.main"]
