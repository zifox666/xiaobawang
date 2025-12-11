FROM python:3.11-slim

WORKDIR /app

ENV TZ Asia/Shanghai
ENV PYTHONPATH=/app

COPY ./docker/start.sh /
RUN chmod +x /start.sh

ENV MAX_WORKERS 1

RUN pip install --no-cache-dir uv
COPY ./pyproject.toml ./uv.lock* /app/

RUN uv sync --frozen
RUN uv run playwright install --with-deps

COPY . /app/

CMD ["/start.sh"]