import argparse
import asyncio
import logging
import sys

import aiohttp

from wyoming.event import Event
from wyoming.info import Describe, Info, HandleProgram, HandleModel, Attribution
from wyoming.asr import Transcript
from wyoming.handle import Handled, NotHandled
from wyoming.server import AsyncEventHandler, AsyncServer

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)


class OllamaHandler(AsyncEventHandler):

    def __init__(
        self,
        reader,
        writer,
        ollama_url: str,
        model: str,
        info: Info,
        system_prompt: str,
    ):
        super().__init__(reader, writer)

        self.ollama_url = ollama_url
        self.model = model
        self.info = info
        self.system_prompt = system_prompt

    async def handle_event(self, event: Event) -> bool:
        logger.info("Received event: %s", event)

        # ---------------------------------------------------------
        # Wyoming Describe
        # ---------------------------------------------------------
        if Describe.is_type(event.type):
            logger.info("Received Describe")
            await self.write_event(self.info.event())
            logger.info("Sent Info")

            return True

        # ---------------------------------------------------------
        # Wyoming Transcript
        # ---------------------------------------------------------
        if Transcript.is_type(event.type):
            transcript = Transcript.from_event(event)
            text = (transcript.text or "").strip()
            logger.info("Transcript: %s", text)

            if not text:
                logger.warning("Transcript is empty")
                await self.write_event(NotHandled(text="No input text!").event())
                return True

            try:
                answer = await self.ask_ollama(text)
                logger.info("Ollama response: %s", answer)

                # -------------------------------------------------
                # Wyoming Handled
                # -------------------------------------------------
                await self.write_event(Handled(text=answer).event())
                logger.info("Sent Handled")

            except Exception as err:
                logger.exception("Ollama request failed")
                await self.write_event(NotHandled(text=str(err)).event())

            return True

        logger.warning(f"Unsupported event type: {event.type,}")

        return True

    async def ask_ollama(self, text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": text,
                }
            ],
            "think": False,
            "stream": False,
        }

        logger.info("Ollama request: model=%s text=%s", self.model, text)

        timeout = aiohttp.ClientTimeout(total=120)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.ollama_url, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(f"Ollama HTTP {response.status}: {body}")

                data = await response.json()

        message = data.get("message", {})

        # Pass only the content to TTS, even when using an Ollama thinking model.
        answer = message.get("content", "")
        answer = answer.strip()

        if not answer:
            raise RuntimeError("Ollama returned empty content")

        return answer


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10500)
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/chat")
    parser.add_argument("--model", default="gemma4:e2b")
    parser.add_argument("--system-prompt", default="You are a voice assistant. Respond briefly. Keep your response to approximately 1 to 3 sentences.")
    args = parser.parse_args()

    attribution = Attribution(
        name="Ollama",
        url="https://ollama.com/",
    )

    handle_model = HandleModel(
        name=args.model,
        attribution=attribution,
        installed=True,
        description="Ollama language model",
        version=None,
        languages=["ja"],
    )

    handle_program = HandleProgram(
        name="ollama",
        attribution=attribution,
        installed=True,
        description="Ollama LLM",
        version=None,
        models=[handle_model],
        supports_handled_streaming=False,
        supports_home_control=False,
    )

    info = Info(handle=[handle_program])

    def handler_factory(reader, writer):
        return OllamaHandler(
            reader=reader,
            writer=writer,
            ollama_url=args.ollama_url,
            model=args.model,
            info=info,
            system_prompt=args.system_prompt,
        )

    uri = f"tcp://{args.host}:{args.port}"
    server = AsyncServer.from_uri(uri)

    logger.debug(f"Wyoming Ollama Wrapper listening on {uri}")
    logger.debug(f"Ollama URL: {args.ollama_url}")
    logger.debug(f"model: {args.model}")
    logger.info("Ready")

    await server.run(handler_factory)


if __name__ == "__main__":
    asyncio.run(main())
