import asyncio
import argparse
import logging
import io
import sys
import wave
from typing import List

from openai import AsyncOpenAI
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.audio import AudioChunk, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info, AsrProgram, AsrModel
from wyoming.asr import Transcribe, Transcript

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger("wyoming-openai-whisper")


class OpenAIWhisperEventHandler(AsyncEventHandler):
    def __init__(
        self,
        *args,
        openai_client: AsyncOpenAI,
        language: str = "ja",
        model: str = "whisper-1",
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.openai_client = openai_client
        self.language = language
        self.model = model
        
        # Buffer for audio data.
        self.audio_bytes = bytearray()
        self.rate = 16000
        self.width = 2
        self.channels = 1

    async def handle_event(self, event: Event) -> bool:
        # Request for client information.
        if Describe.is_type(event.type):
            await self.write_event(
                Info(
                    asr=[
                        AsrProgram(
                            name="OpenAI Whisper Cloud",
                            description="OpenAI Cloud API Whisper STT Wrapper",
                            attribution={"name": "OpenAI", "url": "https://openai.com"},
                            installed=True,
                            version="1.0.0",
                            models=[
                                AsrModel(
                                    name=self.model,
                                    description="OpenAI Whisper 1 Model",
                                    attribution={"name": "OpenAI", "url": "https://openai.com"},
                                    installed=True,
                                    languages=[self.language],
                                )
                            ],
                        )
                    ]
                ).event()
            )
            return True

        # Receive transcription request parameters.
        if Transcribe.is_type(event.type):
            transcribe = Transcribe.from_event(event)
            if transcribe.language:
                self.language = transcribe.language
            return True

        # Receive an audio data chunk.
        if AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            self.rate = chunk.rate
            self.width = chunk.width
            self.channels = chunk.channels
            self.audio_bytes.extend(chunk.audio)
            return True

        # End of audio input (send it to the OpenAI API and return the result).
        if AudioStop.is_type(event.type):
            if not self.audio_bytes:
                logger.warning("Skipping processing because the audio data is empty")
                await self.write_event(Transcript(text="").event())
                return False

            logger.info(f"Sending to the OpenAI Whisper API ({len(self.audio_bytes)} bytes)...")
            
            # Convert to WAV format in memory.
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.width)
                wav_file.setframerate(self.rate)
                wav_file.writeframes(self.audio_bytes)
            
            wav_io.seek(0)
            wav_io.name = "speech.wav"  # Required for the OpenAI API to detect the file extension.

            try:
                # Call the OpenAI API.
                response = await self.openai_client.audio.transcriptions.create(
                    model=self.model,
                    file=wav_io,
                    language=self.language,
                )
                text = response.text.strip()
                logger.info(f"Recognition result: '{text}'")
            except Exception as e:
                logger.error(f"OpenAI API error: {e}")
                text = ""

            # Return the result to the client.
            await self.write_event(Transcript(text=text).event())
            return False

        return True


async def main() -> None:
    parser = argparse.ArgumentParser(description="Wyoming OpenAI Whisper Wrapper")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10300)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--language", default="ja")
    parser.add_argument("--model", default="whisper-1")
    args = parser.parse_args()

    client = AsyncOpenAI(api_key=args.api_key)

    uri = f"tcp://{args.host}:{args.port}"
    server = AsyncServer.from_uri(uri)

    logger.debug(f"Wyoming OpenAI Wrapper listening on {uri}")
    logger.debug(f"language: {args.language}")
    logger.debug(f"model: {args.model}")
    logger.info("Ready")

    await server.run(
        lambda *handler_args: OpenAIWhisperEventHandler(
            *handler_args,
            openai_client=client,
            language=args.language,
            model=args.model,
        )
    )

if __name__ == "__main__":
    asyncio.run(main())