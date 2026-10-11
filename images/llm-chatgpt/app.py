import argparse
import asyncio
import collections
import logging
import os
import sys

from openai import AsyncOpenAI
from wyoming.asr import Transcript
from wyoming.event import Event
from wyoming.handle import Handled, NotHandled
from wyoming.info import Attribution, Describe, HandleModel, HandleProgram, Info
from wyoming.server import AsyncEventHandler, AsyncServer

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)


class ChatGPTHandler(AsyncEventHandler):

    def __init__(
        self,
        reader,
        writer,
        client: AsyncOpenAI,
        model: str,
        info: Info,
        system_prompt: str,
        max_history: int = 5,
    ):
        super().__init__(reader, writer)

        self.client = client
        self.model = model
        self.info = info
        self.system_prompt = system_prompt
        self.max_history = max_history

        # Conversation history (OpenAI API format: [{"role": "user", "content": "..."}, {"role": "assistant", ...}])
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
                answer = await self.ask_chatgpt(text)
                logger.info("ChatGPT response: %s", answer)

                # -------------------------------------------------
                # Wyoming Handled
                # -------------------------------------------------
                await self.write_event(Handled(text=answer).event())
                logger.info("Sent Handled")

            except Exception as err:
                logger.exception("ChatGPT request failed")
                await self.write_event(NotHandled(text=str(err)).event())

            return True

        logger.warning(f"Unsupported event type: {event.type}")
        return True

    async def ask_chatgpt(self, text: str) -> str:
        logger.info("ChatGPT request: model=%s text=%s", self.model, text)

        # 1. Create the user message.
        user_msg = {"role": "user", "content": text}

        # 2. Combine the system prompt, conversation history, and current input.
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(list(self.history))
        messages.append(user_msg)

        # 3. Call the OpenAI Chat Completions API asynchronously.
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )

        answer = (response.choices[0].message.content or "").strip()

        if not answer:
            raise RuntimeError("ChatGPT returned empty content")

        # 4. Update the conversation history (OpenAI role name: "assistant").
        self.history.append(user_msg)
        self.history.append({"role": "assistant", "content": answer})

        return answer


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10500)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--system-prompt", default="You are a voice assistant. Respond briefly. Keep your response to approximately 1 to 3 sentences.")
    parser.add_argument("--max-history", type=int, default=5)
    args = parser.parse_args()

    if not args.api_key:
        logger.error("API Key is required. Set --api-key or OPENAI_API_KEY env.")
        sys.exit(1)

    client = AsyncOpenAI(api_key=args.api_key)

    attribution = Attribution(
        name="OpenAI",
        url="https://openai.com/",
    )

    handle_model = HandleModel(
        name=args.model,
        attribution=attribution,
        installed=True,
        description="OpenAI ChatGPT language model",
        version=None,
        languages=["ja"],
    )

    handle_program = HandleProgram(
        name="chatgpt",
        attribution=attribution,
        installed=True,
        description="OpenAI ChatGPT LLM Wrapper",
        version=None,
        models=[handle_model],
    )

    info = Info(handle=[handle_program])

    def handler_factory(reader, writer):
        return ChatGPTHandler(
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

    logger.debug(f"Wyoming ChatGPT listening on {uri}")
    logger.debug(f"ChatGPT model: {args.model}")
    logger.info("Ready")

    await server.run(handler_factory)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped.")