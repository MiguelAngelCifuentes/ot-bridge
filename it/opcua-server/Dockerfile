FROM python:3.14.7-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10005 opcua && mkdir -p /app/pki && chown opcua /app/pki
USER opcua

EXPOSE 4840
CMD ["python", "main.py"]
