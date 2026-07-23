"""
app/voice/bridge.py — VoiceLive Bridge: proxies audio between browser and Azure OpenAI Realtime.

Architecture:
  Browser WS ←──────────────────────────────────────────────── FastAPI WS
                                                                    │
                        Azure OpenAI Realtime WS ──────────────────┘
                              (STT + GPT-4o + TTS)
                                    │
                        function_call events
                                    │
                        Semantic Kernel plugin execution
                                    │
                        function_call_output → back to Realtime

Wire Protocol (Azure OpenAI Realtime):
  Browser → Server: { type: "audio_chunk", audio: "<base64 pcm16>" }
                    { type: "interrupt" }
                    { type: "ping" }

  Server → Browser: { type: "audio_chunk", audio: "<base64 pcm16>" }
                    { type: "transcript", role: "user"|"assistant", text: "..." }
                    { type: "agent_start" }
                    { type: "agent_stop" }
                    { type: "function_call", name: "...", args: {...} }
                    { type: "error", message: "..." }
                    { type: "status", state: "..." }
                    { type: "session_created", session_id: "..." }
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Optional

import websockets
from fastapi import WebSocket
from semantic_kernel import Kernel

from app.agent.kernel_factory import get_tool_definitions, invoke_plugin_function
from app.agent.system_prompt import get_realtime_session_config
from app.config import get_settings
from app.logging_config import get_logger
from app.voice.session_manager import SessionStatus, VoiceSession

logger = get_logger(__name__)
_settings = get_settings()

# ── Event type constants ───────────────────────────────────────────────────────
_RT_SESSION_UPDATE = "session.update"
_RT_SESSION_CREATED = "session.created"
_RT_INPUT_AUDIO_BUFFER_APPEND = "input_audio_buffer.append"
_RT_INPUT_AUDIO_BUFFER_COMMIT = "input_audio_buffer.commit"
_RT_RESPONSE_CREATE = "response.create"
_RT_RESPONSE_AUDIO_DELTA = "response.audio.delta"
_RT_RESPONSE_AUDIO_DONE = "response.audio.done"
_RT_RESPONSE_DONE = "response.done"
_RT_RESPONSE_CANCEL = "response.cancel"
_RT_INPUT_AUDIO_TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
_RT_RESPONSE_OUTPUT_ITEM_ADDED = "response.output_item.added"
_RT_RESPONSE_TEXT_DELTA = "response.text.delta"
_RT_RESPONSE_FUNCTION_CALL_ARGS_DONE = "response.function_call_arguments.done"
_RT_CONVERSATION_ITEM_CREATE = "conversation.item.create"
_RT_ERROR = "error"


class VoiceLiveBridge:
    """
    Bidirectional proxy between a browser WebSocket and Azure OpenAI Realtime API.

    Responsibilities:
    - Forward raw PCM16 audio from browser to the Realtime API.
    - Receive audio deltas from Realtime API and stream to browser.
    - Intercept function_call events and dispatch to Semantic Kernel plugins.
    - Send typed events to browser (transcript, agent_start/stop, errors).
    - Handle session configuration, interruptions, and graceful shutdown.
    """

    def __init__(
        self,
        browser_ws: WebSocket,
        session: VoiceSession,
        kernel: Kernel,
    ) -> None:
        self._browser = browser_ws
        self._session = session
        self._kernel = kernel
        self._realtime_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._pending_function_calls: dict[str, dict] = {}
        self._current_call_id: Optional[str] = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start the bridge. Connects to Realtime API and runs bidirectional proxy."""
        self._running = True
        try:
            await self._connect_realtime()
            await self._send_browser_event("status", {"state": "connected"})
            self._session.status = SessionStatus.CONNECTED

            # Run both directions concurrently
            await asyncio.gather(
                self._browser_to_realtime_loop(),
                self._realtime_to_browser_loop(),
            )
        except websockets.exceptions.ConnectionClosed as exc:
            logger.info("realtime_connection_closed", session=self._session.session_id, code=exc.code)
        except Exception as exc:
            logger.error("bridge_error", session=self._session.session_id, error=str(exc))
            await self._send_browser_event("error", {"message": "Voice service connection error. Please refresh."})
        finally:
            await self.close()

    async def close(self) -> None:
        """Gracefully close the Realtime WebSocket connection."""
        self._running = False
        if self._realtime_ws:
            state = getattr(self._realtime_ws, "state", None)
            if state != websockets.State.CLOSED:
                try:
                    await self._realtime_ws.close()
                except Exception:
                    pass
        self._session.status = SessionStatus.CLOSED
        logger.info("bridge_closed", session=self._session.session_id)

    # ── Connection ────────────────────────────────────────────────────────────

    async def _connect_realtime(self) -> None:
        """Open WebSocket to Azure OpenAI Realtime endpoint and configure session."""
        url = _settings.realtime_websocket_url
        headers = {
            "api-key": _settings.azure_openai_api_key,
            "OpenAI-Beta": "realtime=v1",
        }

        logger.info("connecting_to_realtime", session=self._session.session_id, url=url.split("?")[0])

        self._realtime_ws = await websockets.connect(
            url,
            additional_headers=headers,
            max_size=10 * 1024 * 1024,  # 10 MB
            ping_interval=20,
            ping_timeout=10,
        )

        # Configure session with tools and voice settings
        await self._configure_realtime_session()

    async def _configure_realtime_session(self) -> None:
        """Send session.update with system prompt, voice, VAD, and tool definitions."""
        config = get_realtime_session_config(voice=_settings.voice_name)

        # Add tool definitions from all registered SK plugins
        tools = get_tool_definitions(self._kernel)
        config["tools"] = tools
        config["tool_choice"] = "auto"

        await self._send_realtime({
            "type": _RT_SESSION_UPDATE,
            "session": config,
        })
        logger.info("realtime_session_configured", tools=len(tools))

    # ── Browser → Realtime loop ───────────────────────────────────────────────

    async def _browser_to_realtime_loop(self) -> None:
        """Forward audio and control messages from browser to Realtime API."""
        try:
            while self._running:
                try:
                    raw = await asyncio.wait_for(
                        self._browser.receive_text(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "audio_chunk":
                    # Forward raw PCM16 audio to Realtime
                    await self._send_realtime({
                        "type": _RT_INPUT_AUDIO_BUFFER_APPEND,
                        "audio": msg["audio"],
                    })
                    self._session.touch()

                elif msg_type == "interrupt":
                    # Cancel the current in-progress response
                    if self._session.current_response_id:
                        await self._send_realtime({"type": _RT_RESPONSE_CANCEL})
                    await self._send_browser_event("agent_stop", {})
                    self._session.is_agent_speaking = False

                elif msg_type == "ping":
                    await self._send_browser_event("pong", {"ts": msg.get("ts")})

        except Exception as exc:
            if self._running:
                logger.error("browser_to_realtime_error", error=str(exc))
            raise

    # ── Realtime → Browser loop ───────────────────────────────────────────────

    async def _realtime_to_browser_loop(self) -> None:
        """Process events from the Realtime API and forward relevant ones to browser."""
        try:
            async for raw_msg in self._realtime_ws:
                if not self._running:
                    break
                try:
                    event = json.loads(raw_msg)
                    await self._handle_realtime_event(event)
                except json.JSONDecodeError:
                    logger.warning("invalid_realtime_message")
                except Exception as exc:
                    logger.error("realtime_event_error", error=str(exc))
        except websockets.exceptions.ConnectionClosed:
            logger.info("realtime_ws_closed", session=self._session.session_id)
            raise

    async def _handle_realtime_event(self, event: dict) -> None:
        """Route a single Realtime API event to the appropriate handler."""
        event_type = event.get("type", "")

        if event_type == _RT_SESSION_CREATED:
            self._session.realtime_session_id = event.get("session", {}).get("id")
            await self._send_browser_event("session_created", {
                "session_id": self._session.realtime_session_id
            })
            self._session.status = SessionStatus.ACTIVE

        elif event_type == "session.updated":
            logger.debug("realtime_session_updated")

        elif event_type == _RT_RESPONSE_AUDIO_DELTA:
            # Stream audio chunk directly to browser
            audio_b64 = event.get("delta", "")
            if audio_b64:
                if not self._session.is_agent_speaking:
                    self._session.is_agent_speaking = True
                    await self._send_browser_event("agent_start", {})
                await self._send_browser_event("audio_chunk", {"audio": audio_b64})

        elif event_type == _RT_RESPONSE_AUDIO_DONE:
            pass  # End of audio for this item — response.done handles cleanup

        elif event_type == _RT_RESPONSE_DONE:
            self._session.is_agent_speaking = False
            self._session.current_response_id = None
            await self._send_browser_event("agent_stop", {})

        elif event_type == _RT_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            transcript = event.get("transcript", "")
            if transcript:
                self._session.add_turn("user", transcript)
                await self._send_browser_event("transcript", {
                    "role": "user",
                    "text": transcript,
                })

        elif event_type == "response.audio_transcript.delta":
            # Streaming assistant transcript
            delta = event.get("delta", "")
            if delta:
                await self._send_browser_event("transcript_delta", {
                    "role": "assistant",
                    "text": delta,
                })

        elif event_type == "response.audio_transcript.done":
            transcript = event.get("transcript", "")
            if transcript:
                self._session.add_turn("assistant", transcript)
                await self._send_browser_event("transcript", {
                    "role": "assistant",
                    "text": transcript,
                })

        elif event_type == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                call_id = item.get("call_id", "")
                self._pending_function_calls[call_id] = {
                    "name": item.get("name", ""),
                    "arguments": "",
                }
                self._current_call_id = call_id

        elif event_type == "response.function_call_arguments.delta":
            call_id = event.get("call_id", "")
            if call_id in self._pending_function_calls:
                self._pending_function_calls[call_id]["arguments"] += event.get("delta", "")

        elif event_type == _RT_RESPONSE_FUNCTION_CALL_ARGS_DONE:
            call_id = event.get("call_id", "")
            if call_id in self._pending_function_calls:
                call_info = self._pending_function_calls.pop(call_id)
                await self._execute_function_call(call_id, call_info)

        elif event_type == _RT_ERROR:
            error_msg = event.get("error", {}).get("message", "Unknown error")
            logger.error("realtime_api_error", error=error_msg, session=self._session.session_id)
            await self._send_browser_event("error", {"message": f"Service error: {error_msg}"})

        elif event_type in ("response.created", "response.output_item.done",
                            "conversation.item.created", "rate_limits.updated",
                            "input_audio_buffer.speech_started",
                            "input_audio_buffer.speech_stopped",
                            "input_audio_buffer.committed"):
            # Forward speech detection events to browser for UI feedback
            if event_type == "input_audio_buffer.speech_started":
                await self._send_browser_event("user_start", {})
            elif event_type == "input_audio_buffer.speech_stopped":
                await self._send_browser_event("user_stop", {})

    # ── Function call execution ───────────────────────────────────────────────

    async def _execute_function_call(self, call_id: str, call_info: dict) -> None:
        """
        Execute a SK plugin function and return the result to the Realtime API.

        The function name from the Realtime API is formatted as "plugin_name-function_name".
        """
        full_name = call_info["name"]
        raw_args = call_info["arguments"]

        logger.info(
            "executing_function_call",
            function=full_name,
            session=self._session.session_id,
        )

        # Notify browser that a function is being called
        await self._send_browser_event("function_call", {
            "name": full_name,
            "status": "running",
        })

        # Parse plugin + function name (format: "plugin_name-function_name")
        if "-" in full_name:
            plugin_name, function_name = full_name.split("-", 1)
        else:
            plugin_name, function_name = full_name, full_name

        # Parse arguments JSON
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            arguments = {}

        # Inject session_id for escalation plugin
        if plugin_name == "escalation" and "session_id" not in arguments:
            arguments["session_id"] = self._session.session_id

        # Execute via Semantic Kernel
        result = await invoke_plugin_function(
            kernel=self._kernel,
            plugin_name=plugin_name,
            function_name=function_name,
            arguments=arguments,
        )

        # Send result back to Realtime API as a conversation item
        await self._send_realtime({
            "type": _RT_CONVERSATION_ITEM_CREATE,
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            },
        })

        # Trigger the model to generate a response based on the function output
        await self._send_realtime({"type": _RT_RESPONSE_CREATE})

        # Notify browser
        await self._send_browser_event("function_call", {
            "name": full_name,
            "status": "done",
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _send_realtime(self, data: dict) -> None:
        """Send a JSON message to the Azure OpenAI Realtime WebSocket."""
        if self._realtime_ws and getattr(self._realtime_ws, "state", None) == websockets.State.OPEN:
            await self._realtime_ws.send(json.dumps(data))

    async def _send_browser_event(self, event_type: str, payload: dict) -> None:
        """Send a typed JSON event to the browser WebSocket."""
        try:
            msg = {"type": event_type, **payload}
            await self._browser.send_text(json.dumps(msg))
        except Exception as exc:
            logger.debug("browser_send_error", error=str(exc))
            self._running = False
