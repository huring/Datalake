FROM python:3.12-alpine

RUN pip install --no-cache-dir supercronic

WORKDIR /scripts

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ .
COPY crontab /crontab

CMD ["supercronic", "/crontab"]
