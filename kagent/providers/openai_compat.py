"""OpenAI-compatible provider.

Hoạt động với:
- Real OpenAI (api.openai.com)
- Self-hosted vLLM / sglang (Qwen, Llama, ...) qua base_url
- LiteLLM gateway

sglang quirk: stream có thể trả thêm field `reasoning_content` cùng `content` —
SDK chuẩn của OpenAI bỏ qua nên ta cũng skip.
"""

import json
import httpx
from openai import AsyncOpenAI

from kagent.providers.base import LLMProvider, LLMResponse, ToolCall, Usage
from kagent.providers.retry import with_retries, stream_with_retries
from kagent.tools.base import ToolResult


# Model substrings (case-insensitive) that support image input.
# `qwen3.6` is a self-hosted Qwen3-VL deployment served under that alias —
# probed and confirmed to accept image_url content blocks.
_VISION_MODEL_HINTS = (
    "gpt-4o", "gpt-4.1", "gpt-5",
    "qwen-vl", "qwen2-vl", "qwen2.5-vl", "qwen3-vl",
    "qwen3.6",
)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        verify_ssl: bool = True,
    ):
        http_client = None
        if not verify_ssl:
            http_client = httpx.AsyncClient(verify=False)
        self.client = AsyncOpenAI(
            api_key=api_key or "EMPTY",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,  # retry tự quản trong providers/retry.py — tắt kẻo retry chồng retry
        )
        self.model = model

    @property
    def supports_image(self) -> bool:
        m = self.model.lower()
        return any(x in m for x in _VISION_MODEL_HINTS)

    @property
    def supports_pdf(self) -> bool:
        # OpenAI Chat API doesn't have document content type — PDF only via image fallback (pdftoppm).
        return False

    async def chat(self, messages, tools=None, system_prompt=None):
        api_messages = self._build_messages(messages, system_prompt)
        kwargs: dict = {"model": self.model, "messages": api_messages}
        if tools:
            kwargs["tools"] = self.format_tools(tools)

        resp = await with_retries(lambda: self.client.chat.completions.create(**kwargs))
        msg = resp.choices[0].message

        text = msg.content or None
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    args=args,
                ))

        usage = Usage(
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )
        return LLMResponse(text=text, tool_calls=tool_calls, usage=usage, raw=resp)

    async def stream_chat(self, messages, tools=None, system_prompt=None):
        """Yield events:
        - {"type": "text", "delta": str}
        - {"type": "tool_call", "call": ToolCall}  — emit AFTER full args collected
        - {"type": "finish", "reason": str}
        - {"type": "usage", "input_tokens": int, "output_tokens": int}

        Retry chỉ áp dụng TRƯỚC first event (sau đó text đã ra màn hình).
        """
        api_messages = self._build_messages(messages, system_prompt)
        kwargs: dict = {
            "model": self.model,
            "messages": api_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = self.format_tools(tools)

        async for event in stream_with_retries(lambda: self._stream_once(kwargs)):
            yield event

    async def _stream_once(self, kwargs: dict):
        """1 lần stream thật — stream_with_retries gọi lại khi attempt mới."""
        # Tool call args stream in chunks — accumulate by index then emit
        tc_acc: dict[int, dict] = {}
        last_finish_reason: str | None = None
        last_usage = None

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if chunk.usage:
                last_usage = chunk.usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                last_finish_reason = choice.finish_reason
            delta = choice.delta
            if delta is None:
                continue
            if getattr(delta, "content", None):
                yield {"type": "text", "delta": delta.content}
            if getattr(delta, "tool_calls", None):
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    acc = tc_acc.setdefault(idx, {"id": "", "name": "", "args_str": ""})
                    if tc_delta.id:
                        acc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc["args_str"] += tc_delta.function.arguments

        for idx in sorted(tc_acc.keys()):
            acc = tc_acc[idx]
            try:
                args = json.loads(acc["args_str"]) if acc["args_str"] else {}
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "call": ToolCall(
                id=acc["id"] or f"call_{acc['name']}",
                name=acc["name"],
                args=args,
            )}

        if last_finish_reason is not None:
            yield {"type": "finish", "reason": last_finish_reason}

        if last_usage is not None:
            yield {
                "type": "usage",
                "input_tokens": last_usage.prompt_tokens or 0,
                "output_tokens": last_usage.completion_tokens or 0,
            }

    def _build_messages(self, messages, system_prompt):
        api: list[dict] = []
        if system_prompt:
            api.append({"role": "system", "content": system_prompt})
        api.extend(self.format_messages(messages))
        return api

    def format_messages(self, messages):
        """Convert normalized messages → OpenAI chat format."""
        out: list[dict] = []
        for msg in messages:
            role = msg["role"]
            # Multimodal user message (content_blocks set by format_tool_result)
            if role == "user" and "content_blocks" in msg:
                content = []
                for b in msg["content_blocks"]:
                    btype = b.get("type")
                    if btype == "text":
                        content.append({"type": "text", "text": b["text"]})
                    elif btype == "image":
                        src = b["source"]
                        data_url = f"data:{src['media_type']};base64,{src['data']}"
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        })
                    # "document" blocks không support — Read tool đã render thành image.
                if content:
                    out.append({"role": "user", "content": content})
                continue

            if role == "user":
                out.append({"role": "user", "content": msg["content"]})
            elif role == "assistant":
                if "tool_calls" in msg:
                    api_msg: dict = {"role": "assistant"}
                    api_msg["content"] = msg.get("text") or None
                    api_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]
                    out.append(api_msg)
                else:
                    out.append({"role": "assistant", "content": msg.get("content", "")})
            elif role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id") or msg.get("id", ""),
                    "content": msg["content"],
                })
        return out

    def format_tool_result(self, tool_call, result):
        """Format tool result. Multimodal → 2 messages (tool text + user image)."""
        # Backward compat: str input (DENY/error path)
        if isinstance(result, str):
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": result,
            }

        # ToolResult text-only
        if not isinstance(result, ToolResult) or not result.is_multimodal():
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": str(result),
            }

        # ToolResult multimodal → 2 messages
        return [
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": result.output or "[image attached in next message]",
            },
            {
                "role": "user",
                "content_blocks": result.content_blocks,
            },
        ]

    def format_tools(self, tools):
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]
