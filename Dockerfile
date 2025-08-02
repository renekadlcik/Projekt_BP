FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libasound2-dev \
    libjack-jackd2-dev \
    libffi-dev \
    libsndfile1 \
    fluidsynth \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

ENV PORT 8080
EXPOSE 8080

CMD ["python", "app.py"]
