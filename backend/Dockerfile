FROM python:3.9-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY start.sh .
COPY prestart.sh .

RUN chmod +x start.sh
RUN chmod +x prestart.sh

CMD ["./start.sh"]