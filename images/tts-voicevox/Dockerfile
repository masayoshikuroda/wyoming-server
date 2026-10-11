FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 10200

ENTRYPOINT ["python", "app.py"]
CMD ["--port", "10200"]

