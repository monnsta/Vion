FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
	gcc \
	libc6-dev \
	git \
	&& rm -rf /var/lib/apt/lists/*

RUN groupadd -r botuser && useradd -r -g botuser botuser

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN chown -R botuser:botuser /app

USER botuser

CMD ["python", "bot.py"]

