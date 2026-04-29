FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps for TA-Lib
RUN apt-get update && apt-get install -y \
    gcc g++ make wget \
    && wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib && ./configure --prefix=/usr && make && make install \
    && cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PORT=8001
EXPOSE 8001

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001} --workers 2
