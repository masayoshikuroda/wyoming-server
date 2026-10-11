import asyncio
import logging
import os
import sys
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)

app = FastAPI()

TCP_HOST = os.getenv("TCP_HOST", "127.0.0.1")
TCP_PORT = int(os.getenv("TCP_PORT", "10500"))

tts_html = Path('tts.html').read_text(encoding='UTF-8')
stt_html = Path('stt.html').read_text(encoding='UTF-8')
llm_html = Path('llm.html').read_text(encoding='UTF-8')

@app.get("/tts")
async def get_tts():
    return HTMLResponse(tts_html)

@app.get("/stt")
async def get_stt():
    return HTMLResponse(stt_html)

@app.get("/llm")
async def get_llm():
    return HTMLResponse(llm_html)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Wyoming WS-TCP Bridge target=tcp://%s:%d", TCP_HOST, TCP_PORT)

def get_client_addr(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else "unknown"
    client_port = websocket.client.port if websocket.client else "unknown"
    return f"{client_host}:{client_port}"
    
async def tcp_to_ws_loop(reader: asyncio.StreamReader, websocket: WebSocket):
    client_addr = get_client_addr(websocket)
    try:    
        while True:
            data = await reader.read(8192)
            if not data:
                logger.info("TCP connection closed by remote target for %s", client_addr)
                break
            logger.info("TCP -> WS (%s): %d bytes", client_addr, len(data))
            await websocket.send_bytes(data)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("Error in TCP -> WS stream (%s): %s", client_addr, e)

async def ws_to_tcp_loop(websocket: WebSocket, writer: asyncio.StreamWriter):
    client_addr = get_client_addr(websocket)
    try:
        while True:
            message = await websocket.receive()
            msg_type = message.get("type")

            if msg_type == "websocket.disconnect":
                logger.info("WebSocket client disconnected: %s", client_addr)
                break

            data = message.get("bytes") or message.get("text", "").encode("utf-8")
            if data:
                logger.info("WS -> TCP (%s): %d bytes", client_addr, len(data))
                writer.write(data)
                await writer.drain()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Error in WS -> TCP stream (%s): %s", client_addr, e)

@app.websocket("/ws")
async def websocket_bridge(websocket: WebSocket):
    client_addr = get_client_addr(websocket)

    await websocket.accept()
    logger.info("WebSocket client connected from %s", client_addr)

    # Connect TCP Server
    try:
        reader, writer = await asyncio.open_connection(TCP_HOST, TCP_PORT)
        logger.info("TCP connection established to %s:%d for %s", TCP_HOST, TCP_PORT, client_addr)
    except Exception as e:
        logger.error("Failed to connect to TCP target %s:%d: %s", TCP_HOST, TCP_PORT, e)
        await websocket.close(code=1011, reason=f"TCP connection failed: {e}")
        return

    # Create task
    tcp_to_ws_task = asyncio.create_task(tcp_to_ws_loop(reader, websocket))
    ws_to_tcp_task = asyncio.create_task(ws_to_tcp_loop(websocket, writer))

    # Wait completion
    done, pending = await asyncio.wait([tcp_to_ws_task, ws_to_tcp_task], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()

    logger.info("Cleaned up connections for %s", client_addr)