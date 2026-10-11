# 軽量な Python 3.11 スリムイメージを使用
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 10200

ENTRYPOINT ["python", "app.py"]
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "10200"]