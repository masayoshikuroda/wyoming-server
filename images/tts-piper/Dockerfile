FROM rhasspy/wyoming-piper:2.5.2

RUN .venv/bin/python3 -m pip install "wyoming-piper[ja]"
RUN .venv/bin/python3 -m pip install "wyoming-piper[th]"

RUN apt-get update
RUN apt-get install -y curl

RUN mkdir -p /data
RUN curl -L https://huggingface.co/rhasspy/piper-voices/resolve/main/ja/ja_JP/hi_fi_captain/medium/ja_JP-hi_fi_captain-medium.onnx -o /data/ja_JP-hi_fi_captain-medium.onnx
RUN curl -L https://huggingface.co/rhasspy/piper-voices/resolve/main/ja/ja_JP/hi_fi_captain/medium/ja_JP-hi_fi_captain-medium.onnx.json -o /data/ja_JP-hi_fi_captain-medium.onnx.json

