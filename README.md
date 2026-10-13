# Wyoming Prococol Servers

Wyoming protocol ベースの音声アシスタント用サーバをコンテナを使って、簡単に起動することができます。
ローカル環境で音声アシスタントを実行するためのバックエンドとして利用します。
TTS / STT / Wake Word Detection / LLM を個別に切り替えられることができます。


## 概要

このプロジェクトは、Wyoming のイベント駆動な音声処理をコンテナで起動するための構成です。
各サービスは独立したコンテナとして動作し、必要に応じて WebSocket ブリッジを通じてブラウザからも接続できます。

主な用途:
- 音声認識（STT）
- 音声合成（TTS）
- Wake Word 検出
- LLM による応答生成
- WebSocket 経由でのブラウザ連携

## 対応サービス

### TTS

- tts-piper
  - `rhasspy/wyoming-piper`を利用
- tts-voicevox
  - VOICEVOX Engine を利用し、音声合成
- tts-gemini
  - Google Gemini 音声合成 API を利用

### STT

- stt-whisper
  - `rhasspy/wyoming-whisper` を利用
- stt-openai
  - OpenAI の音声認識 API を利用
- stt-gemini
  - Gemini の音声認識 API を利用

### Wake Word Detection

- wwd-openwakeword
  - `rhasspy/wyoming-openwakeword` を利用
- wwd-tinykw
  - tinykw

### LLM

- Ollama
  - `llm-ollama`
  - 接続ごとに直近5往復のメッセージ履歴を保持
- ChatGPT
  - `llm-chatgpt`
- Gemini
  - `llm-gemini`

## サービス一覧

`compose.yaml` では以下のサービスが定義されています。

- `tts-piper` : 10200
- `tts-voicevox` : 10201
- `tts-gemini` : 10202
- `stt-whisper` : 10300
- `stt-openai` : 10301
- `stt-gemini` : 10302
- `wwd-openwakeword` : 10400
- `wwd-tinykw` : 10401
- `llm-ollama` : 10500
- `llm-chatgpt` : 10501
- `llm-gemini` : 10502

WebSocket ブリッジを有効にすると以下のポートが使えます。

- `ws-bridge-tts-piper` : 11200
- `ws-bridge-tts-voicevox` : 11201
- `ws-bridge-tts-gemini` : 11302
- `ws-bridge-stt-whisper` : 11300
- `ws-bridge-stt-openai` : 11301
- `ws-bridge-llm-ollama` : 11500
- `ws-bridge-llm-chatgpt` : 11501
- `ws-bridge-llm-gemini` : 11502

## 必要な設定

`.env` ファイルをプロジェクト直下に作成し、必要な API URL / キーを設定します。

```env
VOICEVOX_URL=http://localhost:50021
OLLAMA_URL=http://localhost:11434/api/chat
OPENAI_API_KEY=XXXXXX
GEMINI_API_KEY=XXXXXX
```

- `VOICEVOX_URL` : VOICEVOX Engine の URL
- `OLLAMA_URL` : Ollama の chat API URL
- `OPENAI_API_KEY` : OpenAI API キー
- `GEMINI_API_KEY` : Gemini API キー

## 起動方法

```bash
docker compose up -d
```

必要に応じて WebSocket ブリッジ付きで起動する場合:

```bash
docker compose --profile websocket up -d
```

サービスを停止する場合:

```bash
docker compose down
```

## 使い方

### 1. 対象のコンテナを選ぶ

例えば TTS を使う場合、`tts-voicevox` や `tts-gemini` を選択します。

### 2. Wyoming クライアントから接続する

本構成は Wyoming protocol を直接扱う前提なので、
Home Assistant や Wyoming 対応の音声クライアントから TCP 接続する構成を想定しています。

### 3. ブラウザで確認する

WebSocket ブリッジを使うと、ブラウザから `/tts` / `/stt` / `/llm` のページにアクセスできます。

例:

```text
http://localhost:11200/tts
http://localhost:11300/stt
http://localhost:11500/llm
http://localhost:11501/llm
http://localhost:11502/llm
```
