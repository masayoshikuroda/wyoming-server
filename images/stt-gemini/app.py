import argparse
import asyncio
import logging
import os
import sys

from google import genai
from google.genai import types

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler, AsyncServer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)


class GeminiSpeechEventHandler(AsyncEventHandler):
    def __init__(
        self,
        *args,
        wyoming_info: Info,
        api_key: str,
        model: str = "gemini-3.5-transcribe-live",
        language_code: str = "ja-JP",
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.wyoming_info = wyoming_info
        self.model = model
        self.language_code = language_code
        self.client = genai.Client(api_key=api_key)
        self.gemini_session = None
        self.receive_task = None
        self.sample_rate = 16000
        self.channels = 1

    async def _start_gemini(self) -> None:
        logger.info("Connecting Gemini Live: model=%s language=%s", self.model, self.language_code)

        self.gemini_context = self.client.aio.live.connect(
            model=self.model,
            config=types.LiveConnectConfig(
                response_modalities=["TEXT"],
                input_audio_transcription=types.AudioTranscriptionConfig(
                    language_codes=[self.language_code]
                )
            )
        )

        self.gemini_session = await self.gemini_context.__aenter__()
        logger.info("Gemini Live connected")

        # Geminiからの文字起こし受信を開始
        self.receive_task = asyncio.create_task(self._receive_gemini())

    async def _stop_gemini(self) -> None:
        if self.gemini_session is None:
            return

        try:
            logger.info("Ending Gemini audio stream")
            await self.gemini_session.send_realtime_input(audio_stream_end=True)
        except Exception:
            logger.exception("Failed to send audio_stream_end")

        # 受信側が最後のtranscriptionを受け取る時間を確保
        if self.receive_task is not None:
            try:
                await asyncio.wait_for(self.receive_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Gemini receive timeout")
                self.receive_task.cancel()
                try:
                    await self.receive_task
                except asyncio.CancelledError:
                    pass
            except Exception:
                logger.exception("Gemini receive task failed")

        try:
            await self.gemini_context.__aexit__(None, None, None)
        except Exception:
            logger.exception("Failed to close Gemini Live")

        self.gemini_session = None
        self.gemini_context = None
        self.receive_task = None

        logger.info("Gemini Live disconnected")


    async def _receive_gemini(self) -> None:
        try:
            while True:
                async for response in self.gemini_session.receive():
                    server_content = response.server_content
                    if server_content is None:
                        continue

                    transcription = (server_content.input_transcription)
                    if transcription is not None:
                        text = transcription.text or ""
                        if text:
                            logger.info("Gemini transcript: %s", text)

                            # Wyomingへリアルタイムで返す
                            await self.write_event(
                                Transcript(text=text).event()
                            )

                    # audio_stream_end後の最終応答
                    if server_content.turn_complete:
                        logger.info("Gemini turn complete")
                        break

                # SDKの receive() は turn_complete で終了する
                #
                # audio_stream_end後は、このセッションでは
                # これ以上受信する必要がない。
                break

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception("Error receiving Gemini transcription")

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            logger.debug( "Received Describe request")
            await self.write_event(self.wyoming_info.event())
            return True

        if Transcribe.is_type(event.type):
            transcribe = Transcribe.from_event(event)

            if transcribe.language:
                self.language_code = ( transcribe.language )
                logger.info( "Language: %s", self.language_code)

            # 新しい発話開始
            await self._start_gemini()

            return True

        if AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)

            self.sample_rate = chunk.rate
            self.channels = chunk.channels

            if self.gemini_session is None:
                # Transcribeイベントが来ないクライアントへの保険
                await self._start_gemini()

            # Wyoming PCMをそのままGeminiへ送信
            await self.gemini_session.send_realtime_input(
                audio=types.Blob(
                    data=chunk.audio,
                    mime_type=( f"audio/pcm;rate={chunk.rate}")
                )
            )

            logger.debug("AudioChunk: %d bytes, %d Hz, %d ch", chunk.rate, chunk.channels)
            return True

        if AudioStop.is_type(event.type):
            logger.info("AudioStop")
            await self._stop_gemini()
            return False
        
        return True

async def main() -> None:
    parser = argparse.ArgumentParser(description="Wyoming Gemini Live Transcript Wrapper")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10300)
    parser.add_argument("--model", type=str, default="gemini-3.5-transcribe-live")
    parser.add_argument("--language", type=str, default="ja-JP")
    parser.add_argument("--api-key", type=str, default=os.environ.get("GEMINI_API_KEY", ""))
    args = parser.parse_args()

    wyoming_info = Info(
        asr=[
            AsrProgram(
                name="gemini-speech-to-text",
                description=(
                    "Gemini Live Speech-to-Text "
                    "wrapper for Wyoming"
                ),
                attribution=Attribution(
                    name="Google Gemini",
                    url=(
                        "https://ai.google.dev/"
                        "gemini-api/docs/live-api/"
                        "live-transcribe"
                    ),
                ),
                installed=True,
                version="2.0.0",
                models=[
                    AsrModel(
                        name=args.model,
                        description=(
                            "Gemini Live "
                            "transcription model"
                        ),
                        attribution=Attribution(
                            name="Google Gemini",
                            url=(
                                "https://ai.google.dev/"
                                "gemini-api/docs/live-api/"
                                "live-transcribe"
                            ),
                        ),
                        installed=True,
                        languages=[args.language],
                        version="2.0.0",
                    )
                ],
            )
        ]
    )

    uri = f"tcp://{args.host}:{args.port}"
    server = AsyncServer.from_uri(uri)

    logger.debug("Wyoming Gemini Live STT listening on %s",uri)
    logger.debug("Model: %s", args.model)
    logger.debug("Language: %s",args.language)
    logger.info("Ready")

    await server.run(
        lambda *s_args, **s_kwargs:
            GeminiSpeechEventHandler(
                *s_args,
                wyoming_info=wyoming_info,
                api_key=args.api_key,
                model=args.model,
                language_code=args.language,
                **s_kwargs,
            )
    )

if __name__ == "__main__":
    asyncio.run(main())
