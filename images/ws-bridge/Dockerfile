FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

COPY main.py .
COPY tts.html .
COPY stt.html .
COPY llm.html .
COPY key.pem . 
COPY cert.pem .

EXPOSE 8000

ENTRYPOINT ["uvicorn", "main:app"]
CMD ["--host", "0.0.0.0", "--port", "8000"]