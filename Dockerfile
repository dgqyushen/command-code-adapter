FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-cache --no-interaction --no-ansi --only main

COPY . .

EXPOSE 8080

CMD ["uvicorn", "cc_adapter.main:app", "--host", "0.0.0.0", "--port", "8080"]
