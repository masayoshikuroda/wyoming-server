import argparse
import asyncio
import io
import logging
import sys
import wave
import aiohttp

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s]:%(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)


class VoicevoxEventHandler(AsyncEventHandler):

    def __init__(
        self,
        *args,
        wyoming_info: Info = None,
        voicevox_url: str = "http://localhost:50021",
        default_speaker: int = 3,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.wyoming_info = wyoming_info
        self.voicevox_url = voicevox_url
        self.default_speaker = default_speaker

    async def handle_event(self, event: Event) -> bool:
        # Describe request
        if Describe.is_type(event.type):
            logger.debug("Received Describe request")
            await self.write_event(self.wyoming_info.event())
            return True

        # Synthesize request
        if Synthesize.is_type(event.type):
            synthesize = Synthesize.from_event(event)
            text = synthesize.text
            speaker_id = self.default_speaker

            # Voice specified (speaker ID)
            if synthesize.voice and synthesize.voice.name:
                try:
                    speaker_id = int(synthesize.voice.name)
                except ValueError:
                    logger.warning(
                        f"Invalid speaker ID specified: '{synthesize.voice.name}'. Using default ({self.default_speaker})."
                    )

            logger.info(
                f"Starting synthesis: '{text}' (Speaker ID: {speaker_id})"
            )

            try:
                async with aiohttp.ClientSession() as session:
                    # 1. Create speech synthesis query
                    async with session.post(
                        f"{self.voicevox_url}/audio_query",
                        params={"text": text, "speaker": speaker_id},
                    ) as resp:
                        if resp.status != 200:
                            logger.error(
                                f"VOICEVOX audio_query error: Status {resp.status}"
                            )
                            return True
                        query = await resp.json()

                    # 2. Generate speech (retrieve WAV data)
                    async with session.post(
                        f"{self.voicevox_url}/synthesis",
                        params={"speaker": speaker_id},
                        json=query,
                    ) as resp:
                        if resp.status != 200:
                            logger.error(
                                f"VOICEVOX synthesis error: Status {resp.status}"
                            )
                            return True
                        wav_data = await resp.read()

                # 3. Parse WAV header and extract PCM data
                with wave.open(io.BytesIO(wav_data), "rb") as wav_file:
                    rate = wav_file.getframerate()
                    width = wav_file.getsampwidth()
                    channels = wav_file.getnchannels()
                    pcm_data = wav_file.readframes(wav_file.getnframes())

                # 4. Stream Wyoming events
                await self.write_event(
                    AudioStart(
                        rate=rate, width=width, channels=channels
                    ).event()
                )

                chunk_size = 4096
                for i in range(0, len(pcm_data), chunk_size):
                    chunk = pcm_data[i : i + chunk_size]
                    await self.write_event(
                        AudioChunk(
                            audio=chunk,
                            rate=rate,
                            width=width,
                            channels=channels,
                        ).event()
                    )

                await self.write_event(AudioStop().event())
                logger.info(f"Synthesis completed and sent: '{text}'")

            except Exception as e:
                logger.exception(f"An exception occurred during synthesis: {e}")

        return True


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10200)
    parser.add_argument("--voicevox-url", type=str, default="http://localhost:50021")
    parser.add_argument("--default-speaker", type=int, default=3)
    args = parser.parse_args()

    wyoming_info = Info(
        tts=[
            TtsProgram(
                name="voicevox",
                description="VOICEVOX TTS Wrapper for Wyoming",
                attribution=Attribution(
                    name="VOICEVOX", url="https://voicevox.hiroshiba.jp/"
                ),
                installed=True,
                version="1.0",
                voices=[
                    TtsVoice(
                        name=str(args.default_speaker),
                        description="Default Voice",
                        attribution=Attribution(
                            name="VOICEVOX",
                            url="https://voicevox.hiroshiba.jp/",
                        ),
                        installed=True,
                        languages=["ja"],
                        version="1.0",
                    )
                ],
            )
        ]
    )

    uri = f"tcp://{args.host}:{args.port}"
    server = AsyncServer.from_uri(uri)

    logger.debug(f"Wyoming VOICEVOX Wrapper listening on {uri}")
    logger.debug(f"VOICEVOX URL: {args.voicevox_url}")
    logger.debug(f"VOICEVOX Default Speaker: {args.default_speaker}")
    logger.info("Ready")

    await server.run(
        lambda *s_args, **s_kwargs: VoicevoxEventHandler(
            *s_args,
            wyoming_info=wyoming_info,
            voicevox_url=args.voicevox_url,
            default_speaker=args.default_speaker,
            **s_kwargs,
        )
    )
    logger.info("Ready")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped.")