FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir requests

COPY simulateur.py .

EXPOSE 8001
CMD ["python", "simulateur.py", "--url", "http://backend:8000", "--hote-controle", "0.0.0.0"]
