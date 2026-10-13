import argparse
import asyncio
import base64
import logging
import os
import sys

from google import genai
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize, SynthesizeVoice

# -----------------------------------------------------------------------------
# Logging configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)


class GeminiTtsEventHandler(AsyncEventHandler):
    def __init__(
        self,
        *args,
        api_key: str,
        wyoming_info: Info,
        model: str = "gemini-3.8-flash-tts",
        voice_name: str = "Kore",
        language_code: str = "ja-JP",
        sample_rate: int = 16000,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.wyoming_info = wyoming_info
        self.model = model
        self.voice_name = voice_name
        self.language_code = language_code
        self.sample_rate = sample_rate
        self.client = genai.Client(api_key=api_key)

    async def handle_event(self, event: Event) -> bool:
        # 1. Describe request (メタデータの返却)
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True

        # 2. Synthesize request (音声合成のリクエスト)
        if Synthesize.is_type(event.type):
            synthesize = Synthesize.from_event(event)
            text = synthesize.text

            # リクエスト側から音声（ボイス）指定がある場合の処理
            voice_name = self.voice_name
            language_code = self.language_code
            if synthesize.voice:
                if synthesize.voice.name:
                    voice_name = synthesize.voice.name
                if synthesize.voice.language:
                    language_code = synthesize.voice.language

            logger.info(f"Synthesizing text: '{text}' (voice: {voice_name}, lang: {language_code})")

            await self._synthesize_and_stream(text, voice_name, language_code)
            return False

        return True

    async def _synthesize_and_stream(
        self, text: str, voice_name: str, language_code: str
    ) -> None:
        """Gemini TTS で合成し、PCM 音声を Wyoming イベントで送信する。"""
        try:
            interaction = await asyncio.to_thread(
                self.client.interactions.create,
                model=self.model,
                input=[
                    {
                        "type": "user_input",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
                response_format={
                    "type": "audio",
                    "mime_type": "audio/l16",
                    "sample_rate": self.sample_rate,
                },
                generation_config={"speech_config": [{"voice": voice_name}]},
            )
            audio_output = interaction.output_audio
            if not audio_output or not audio_output.data:
                logger.error("No audio content received from Gemini TTS API.")
                return

            pcm_data = base64.b64decode(audio_output.data)

            # 1. AudioStart イベントを送信
            await self.write_event(
                AudioStart(
                    rate=self.sample_rate,
                    width=2,   # 16-bit (2 bytes per sample)
                    channels=1 # モノラル
                ).event()
            )

            # 2. 音声データをチャンク単位 (1024バイトずつ) に分割して送信
            chunk_size = 1024
            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i : i + chunk_size]
                await self.write_event(
                    AudioChunk(
                        audio=chunk,
                        rate=self.sample_rate,
                        width=2,
                        channels=1,
                    ).event()
                )

            # 3. AudioStop イベントを送信してストリーム終了を通知
            await self.write_event(AudioStop().event())
            logger.info("Audio streaming completed successfully.")

        except Exception as e:
            logger.exception(f"An error occurred during Gemini TTS request: {e}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10200)
    parser.add_argument("--model", type=str, default="gemini-3.8-flash-tts")
    parser.add_argument("--voice", type=str, default="Kore")
    parser.add_argument("--language", type=str, default="ja-JP")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--api-key", type=str, default=os.environ.get("GEMINI_API_KEY", ""))
    args = parser.parse_args()

    wyoming_info = Info(
        tts=[
            TtsProgram(
                name="gemini-text-to-speech",
                description="Gemini Text-to-Speech wrapper for Wyoming",
                attribution=Attribution(
                    name="Google Gemini",
                    url="https://ai.google.dev/gemini-api/docs/speech-generation",
                ),
                installed=True,
                version="1.0.0",
                voices=[
                    TtsVoice(
                        name=args.voice,
                        description=f"Gemini TTS Voice ({args.voice})",
                        attribution=Attribution(
                            name="Google Gemini",
                            url="https://ai.google.dev/gemini-api/docs/speech-generation",
                        ),
                        installed=True,
                        languages=[args.language],
                        version="1.0.0",
                    )
                ],
            )
        ]
    )

    uri = f"tcp://{args.host}:{args.port}"
    server = AsyncServer.from_uri(uri)

    logger.debug(f"Wyoming Gemini TTS client listening on {uri}")
    logger.debug(f"model: {args.model}, voice: {args.voice}")
    logger.info("Ready")

    await server.run(
        lambda *s_args, **s_kwargs: GeminiTtsEventHandler(
            *s_args,
            api_key=args.api_key,
            wyoming_info=wyoming_info,
            model=args.model,
            voice_name=args.voice,
            language_code=args.language,
            sample_rate=args.sample_rate,
            **s_kwargs,
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped.")