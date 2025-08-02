FROM python:3.9-slim

# 1. Nainstaluj systémové závislosti
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libasound2-dev \
        libffi-dev \
        libglib2.0-0 \
        libsmf-dev \
        pkg-config \
        git \
        fluidsynth \
        && rm -rf /var/lib/apt/lists/*

# 2. Nastav pracovní adresář
WORKDIR /app

# 3. Zkopíruj requirements.txt do kontejneru
COPY requirements.txt .

# 4. Upgraduj pip a nainstaluj numpy předem (DŮLEŽITÉ!)
RUN pip install --upgrade pip
RUN pip install numpy

# 5. Nainstaluj všechny závislosti
RUN pip install -r requirements.txt

# 6. Zkopíruj celý projekt
COPY . .

# 7. Nastav port (pro Railway je obvykle 8080)
ENV PORT 8080

# 8. Startovací příkaz
CMD ["python", "app.py"]
