FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 10300

ENTRYPOINT ["python", "app.py"]
CMD ["--host", "0.0.0.0", "--port", "10300", "--language", "ja-JP"]