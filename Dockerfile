FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg nodejs npm git fontconfig fonts-dejavu-core fonts-montserrat \
    && if [ ! -e /usr/local/bin/node ] && command -v nodejs >/dev/null; then ln -s "$(command -v nodejs)" /usr/local/bin/node; fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
