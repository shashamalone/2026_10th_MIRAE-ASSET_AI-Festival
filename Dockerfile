FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY src /app/src
COPY ontology /app/ontology
COPY metadata /app/metadata
COPY sql /app/sql
COPY docs/docs_data_layer /app/docs/docs_data_layer
COPY expected_question /app/expected_question

CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
