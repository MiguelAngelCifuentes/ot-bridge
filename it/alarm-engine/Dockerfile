FROM python:3.11.16-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10004 alarm
RUN mkdir -p /app/data && chown -R alarm:alarm /app/data
USER alarm

CMD ["python", "main.py"]
