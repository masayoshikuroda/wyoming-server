# Dockerfile
FROM python:3.11-slim

# 必要なパッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# リポジトリのクローン
WORKDIR /app
RUN git clone https://github.com/Yamawine408/wyoming-tinykw.git .

# 依存関係のインストール（TinyKWのパッケージも含まれます）
RUN pip install --no-cache-dir .

COPY okay_nabu.json .

# Wyomingプロトコルのポート（デフォルト10400）を公開
EXPOSE 10400

# 実行コマンドの定義
ENTRYPOINT ["python3", "-m", "wyoming_tinykw"]
CMD ["--uri", "tcp://0.0.0.0:10400", "--keyword-file", "/app/okay_nabu.json", "--keyword-name", "ok_nabu", "--language", "ja", "--threshold", "0.50"]
