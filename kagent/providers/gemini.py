import base64

from google import genai
from google.genai import types
from kagent.providers.base import LLMProvider, LLMResponse, ToolCall, Usage
from kagent.providers.retry import with_retries, stream_with_retries
from kagent.tools.base import ToolResult


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    @property
    def supports_pdf(self) -> bool:
        return True

    @property
    def supports_image(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        """Model chat-capable từ models.list (chỉ giữ generateContent)."""
        names: list[str] = []
        async for m in await self.client.aio.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if "generateContent" in actions:
                names.append((m.name or "").removeprefix("models/"))
        return names

    async def chat(self, messages, tools=None, system_prompt=None):
        contents = self.format_messages(messages)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
        )

        if tools:
            config.tools = self.format_tools(tools)

        # client.aio = async mirror của google-genai SDK — sync client sẽ
        # block event loop (cancellation/ESC watcher không chạy được).
        response = await with_retries(lambda: self.client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        ))

        # Parse text — skip thought summary parts (Gemini 3 thinking model)
        text = None
        if response.candidates:
            text_pieces = [
                p.text
                for p in response.candidates[0].content.parts
                if getattr(p, "text", None) and not getattr(p, "thought", False)
            ]
            if text_pieces:
                text = "".join(text_pieces)

        # Parse tool calls
        tool_calls = []
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    meta: dict = {}
                    sig = getattr(part, "thought_signature", None)
                    if sig is not None:
                        meta["thought_signature"] = sig
                    tool_calls.append(ToolCall(
                        id=f"call_{part.function_call.name}",
                        name=part.function_call.name,
                        args=dict(part.function_call.args),
                        provider_metadata=meta,
                    ))

        # Parse usage
        usage = Usage(
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

        return LLMResponse(text=text, tool_calls=tool_calls, usage=usage, raw=response)

    async def stream_chat(self, messages, tools=None, system_prompt=None):
        """Yield events từ stream:

        - {"type": "text", "delta": str} — token text chunk
        - {"type": "tool_call", "call": ToolCall} — function call
        - {"type": "usage", "input_tokens": int, "output_tokens": int} — emit 1 lần ở cuối

        Retry chỉ áp dụng TRƯỚC first event (sau đó text đã ra màn hình).
        """
        contents = self.format_messages(messages)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
        )
        if tools:
            config.tools = self.format_tools(tools)

        async for event in stream_with_retries(lambda: self._stream_once(contents, config)):
            yield event

    async def _stream_once(self, contents, config):
        """1 lần stream thật — stream_with_retries gọi lại khi attempt mới."""
        last_usage = None
        last_finish_reason = None
        stream = await self.client.aio.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if chunk.usage_metadata:
                last_usage = chunk.usage_metadata
            if not chunk.candidates:
                continue
            cand = chunk.candidates[0]
            if getattr(cand, "finish_reason", None):
                last_finish_reason = cand.finish_reason
            if cand.content is None or cand.content.parts is None:
                continue
            for part in cand.content.parts:
                # Skip thought summary parts (Gemini 3 thinking model) — they
                # contain interim reasoning that duplicates the final answer
                # and would pollute text_acc in the engine.
                if getattr(part, "thought", False):
                    continue
                if getattr(part, "text", None):
                    yield {"type": "text", "delta": part.text}
                elif getattr(part, "function_call", None):
                    meta: dict = {}
                    sig = getattr(part, "thought_signature", None)
                    if sig is not None:
                        meta["thought_signature"] = sig
                    yield {"type": "tool_call", "call": ToolCall(
                        id=f"call_{part.function_call.name}",
                        name=part.function_call.name,
                        args=dict(part.function_call.args),
                        provider_metadata=meta,
                    )}

        if last_finish_reason is not None:
            reason = getattr(last_finish_reason, "name", str(last_finish_reason))
            yield {"type": "finish", "reason": reason}

        if last_usage is not None:
            yield {
                "type": "usage",
                "input_tokens": last_usage.prompt_token_count or 0,
                "output_tokens": last_usage.candidates_token_count or 0,
            }

    def format_messages(self, messages):
        """Convert normalized messages to Gemini Content format.

        4 loại message:
        1. User text       → Content(role="user", parts=[Part(text=...)])
        2. User multimodal → Content(role="user", parts=[Part.from_bytes(...) ...])
        3. Assistant+tools → Content(role="model", parts=[Part(function_call=...), ...])
        4. Tool result     → Content(role="user", parts=[Part(function_response=...)])
        """
        contents = []
        for msg in messages:
            role = msg["role"]

            # Multimodal user message (content_blocks set by format_tool_result)
            if role == "user" and "content_blocks" in msg:
                parts = self._blocks_to_parts(msg["content_blocks"])
                contents.append(types.Content(role="user", parts=parts))
                continue

            if role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=msg["content"])],
                ))

            elif role == "assistant":
                if "tool_calls" in msg:
                    parts = []
                    if msg.get("text"):
                        parts.append(types.Part(text=msg["text"]))
                    for tc in msg["tool_calls"]:
                        meta = tc.get("provider_metadata") or {}
                        sig = meta.get("thought_signature")
                        part_kwargs = {
                            "function_call": types.FunctionCall(
                                name=tc["name"],
                                args=tc["args"],
                            )
                        }
                        if sig is not None:
                            part_kwargs["thought_signature"] = sig
                        parts.append(types.Part(**part_kwargs))
                    contents.append(types.Content(role="model", parts=parts))
                else:
                    contents.append(types.Content(
                        role="model",
                        parts=[types.Part(text=msg.get("content", ""))],
                    ))

            elif role == "tool":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(
                        function_response=types.FunctionResponse(
                            name=msg["name"],
                            response={"result": msg["content"]},
                        )
                    )],
                ))

        return contents

    def format_tool_result(self, tool_call, result):
        """Format tool result cho message history (normalized format).

        Multimodal flow: tool_result chỉ chấp nhận text trong functionResponse.
        Để gửi PDF/image, ta trả 2 messages:
          1) tool role với preview text (functionResponse)
          2) user role với content_blocks → format_messages convert sang inline_data
        """
        # Backward compat: str input (DENY/error path)
        if isinstance(result, str):
            return {"role": "tool", "name": tool_call.name, "content": result}

        # ToolResult text-only
        if not isinstance(result, ToolResult) or not result.is_multimodal():
            return {
                "role": "tool",
                "name": tool_call.name,
                "content": str(result),
            }

        # ToolResult multimodal → 2 messages
        return [
            {
                "role": "tool",
                "name": tool_call.name,
                "content": result.output or "[multimodal attachment in next message]",
            },
            {
                "role": "user",
                "content_blocks": result.content_blocks,
            },
        ]

    def _blocks_to_parts(self, blocks: list[dict]) -> list:
        """Convert normalized content blocks → Gemini Parts (inline_data)."""
        parts = []
        for b in blocks:
            btype = b.get("type")
            if btype == "text":
                parts.append(types.Part.from_text(text=b["text"]))
            elif btype in ("document", "image"):
                src = b["source"]
                raw = base64.b64decode(src["data"])
                parts.append(types.Part.from_bytes(
                    data=raw,
                    mime_type=src["media_type"],
                ))
        return parts

    def format_tools(self, tools):
        """Convert tool schemas (JSON Schema) → Gemini FunctionDeclaration."""
        declarations = []
        for tool in tools:
            declarations.append(types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=tool["input_schema"],
            ))
        return [types.Tool(function_declarations=declarations)]
