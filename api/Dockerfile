FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY routers ./routers
COPY migrations ./migrations

EXPOSE 8000

CMD ["python", "main.py"]
