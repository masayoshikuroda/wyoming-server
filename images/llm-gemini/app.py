import argparse
import asyncio
import collections
import logging
import os
import sys
from typing import List

from google import genai
from google.genai import types
from wyoming.asr import Transcript
from wyoming.event import Event
from wyoming.handle import Handled, NotHandled
from wyoming.info import Attribution, Describe, HandleModel, HandleProgram, Info
from wyoming.server import AsyncEventHandler, AsyncServer

# -----------------------------------------------------------------------------
# Logging configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)


class GeminiHandler(AsyncEventHandler):

    def __init__(
        self,
        reader,
        writer,
        client: genai.Client,
        model: str,
        info: Info,
        system_prompt: str,
        max_history: int = 10,
    ):
        super().__init__(reader, writer)

        self.client = client
        self.model = model
        self.info = info
        self.system_prompt = system_prompt
        self.max_history = max_history

        # Conversation history corresponding to C++ std::deque history.
        # Gemini API format: [{"role": "user", "parts": [{"text": "..."}]}, {"role": "model", ...}]
        self.history: collections.deque = collections.deque(maxlen=self.max_history * 2)

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
                answer = await self.ask_gemini(text)
                logger.info("Gemini response: %s", answer)

                # -------------------------------------------------
                # Wyoming Handled
                # -------------------------------------------------
                await self.write_event(Handled(text=answer).event())
                logger.info("Sent Handled")

            except Exception as err:
                logger.exception("Gemini request failed")
                await self.write_event(NotHandled(text=str(err)).event())

            return True

        logger.warning(f"Unsupported event type: {event.type}")
        return True

    async def ask_gemini(self, text: str) -> str:
        logger.info("Gemini request: model=%s text=%s", self.model, text)

        # 1. Add user input to the history (equivalent to
        #    C++ history.push_back({"user", question})).
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=text)],
        )
        contents_payload = list(self.history) + [user_content]

        # 2. Call the Google GenAI API in a worker thread.
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model,
                contents=contents_payload,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    max_output_tokens=300,
                ),
            ),
        )

        # Validate the response, equivalent to C++ selectAnswer.
        answer = (response.text or "").strip()

        if not answer:
            raise RuntimeError("Gemini returned empty content or answer key not found")

        # Safety check corresponding to the C++ "Thank you for watching" error check.
        if answer == "ご視聴ありがとうございました":
            raise RuntimeError("Failed to get valid answer from Gemini response")

        # 3. Update the history after a successful response (equivalent to
        #    C++ history.push_back({"model", answer})).
        self.history.append(user_content)
        self.history.append(
            types.Content(
                role="model",  # Gemini API uses "model" rather than "assistant".
                parts=[types.Part.from_text(text=answer)],
            )
        )

        return answer


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10500)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--system-prompt", default="You are a voice assistant. Respond briefly. Keep your response to approximately 1 to 3 sentences in English.",)
    parser.add_argument("--max-history", type=int, default=5)
    args = parser.parse_args()

    if not args.api_key:
        logger.error("API Key is required. Set --api-key")
        sys.exit(1)

    client = genai.Client(api_key=args.api_key)

    attribution = Attribution(
        name="Google",
        url="https://ai.google.dev/",
    )

    handle_model = HandleModel(
        name=args.model,
        attribution=attribution,
        installed=True,
        description="Google Gemini language model",
        version=None,
        languages=["ja"],
    )

    handle_program = HandleProgram(
        name="gemini",
        attribution=attribution,
        installed=True,
        description="Google Gemini LLM Wrapper",
        version=None,
        models=[handle_model],
    )

    info = Info(handle=[handle_program])

    def handler_factory(reader, writer):
        return GeminiHandler(
            reader=reader,
            writer=writer,
            client=client,
            model=args.model,
            info=info,
            system_prompt=args.system_prompt,
            max_history=args.max_history,
        )

    uri = f"tcp://{args.host}:{args.port}"
    server = AsyncServer.from_uri(uri)

    logger.debug(f"Wyoming Gemini Warpper listening on {uri}")
    logger.debug(f"model: {args.model}")
    logger.info("Ready")

    await server.run(handler_factory)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped.")