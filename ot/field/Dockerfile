FROM python:3.11.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OTB_FIELD_BIND=0.0.0.0

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
RUN useradd --system --uid 10010 field
USER field

EXPOSE 5020 5021 5022
CMD ["python", "-u", "main.py", "--headless"]
