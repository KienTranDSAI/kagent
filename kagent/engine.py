"""Agentic Loop với parallel tool execution.

Flow:
  auto-compact → stream LLM → text_only? → done
                            → tool_calls? → batch partition
                                            → execute (parallel read-only / sequential write)
                                            → loop back
"""

import asyncio
import os
import time

from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from kagent.providers.base import LLMProvider, ToolCall
from kagent.tools.base import Tool, ToolContext, ToolResult
from kagent.tools.registry import ToolRegistry
from kagent.context import build_system_prompt
from kagent.permissions.types import PermissionDecision
from kagent.permissions.checker import PermissionChecker
from kagent.conversation import (
    estimate_messages_tokens,
    get_context_window,
    micro_compact,
    compact_conversation,
    CostTracker,
    ContextTracker,
    resolve_context_tokens,
)
from kagent.ui.terminal import (
    console,
    tool_spinner,
    print_tool_call,
    print_tool_result,
    print_tool_error,
    print_info,
)

MAX_TURNS = int(os.getenv("KAGENT_MAX_TURNS", "50"))
AUTOCOMPACT_BUFFER = 13_000
OUTPUT_RESERVE = 8_000

# Normal finish reasons across providers — don't log as noise.
# Gemini: STOP / FINISH_REASON_UNSPECIFIED
# OpenAI/sglang: stop / tool_calls
# Anthropic: end_turn / tool_use
NORMAL_FINISH_REASONS = {
    "STOP", "FINISH_REASON_UNSPECIFIED",
    "stop", "tool_calls",
    "end_turn", "tool_use",
}


async def agent_loop(
    messages: list[dict],
    provider: LLMProvider,
    registry: ToolRegistry,
    system_prompt: str | None = None,
    permission_checker: PermissionChecker | None = None,
    cost_tracker: CostTracker | None = None,
    model: str | None = None,
    context_tracker: ContextTracker | None = None,
) -> str:
    """Core agentic loop: streaming UI + auto-compact + cost tracking + parallel tools."""
    if system_prompt is None:
        has_todo = registry.get("TodoWrite") is not None
        has_plan = registry.get("EnterPlanMode") is not None
        has_multimodal = provider.supports_pdf or provider.supports_image
        system_prompt = build_system_prompt(
            with_todo=has_todo,
            with_plan_mode=has_plan,
            with_multimodal=has_multimodal,
        )

    tool_schemas = registry.get_schemas_for_llm()
    context = ToolContext(cwd=os.getcwd())
    turn = 0
    context_window = get_context_window(model or "")
    threshold = context_window - AUTOCOMPACT_BUFFER - OUTPUT_RESERVE

    while True:
        turn += 1
        if turn > MAX_TURNS:
            return "[Reached maximum turns limit. Stopping.]"

        # Auto-compact check — ưu tiên usage THẬT từ API call gần nhất
        current, source = resolve_context_tokens(messages, context_tracker)
        if current > threshold:
            print_info(f"[auto-compact] {current:,} ({source}) > {threshold:,} — tier 1")
            messages[:] = micro_compact(messages)
            if context_tracker is not None:
                context_tracker.reset()  # context đã đổi → số API cũ stale
            after = estimate_messages_tokens(messages)
            print_info(f"[auto-compact] tier 1: {after:,} tokens")
            if after > threshold:
                print_info("[auto-compact] tier 3 (LLM summary)...")
                messages[:] = await compact_conversation(messages, provider)
                print_info(f"[auto-compact] tier 3: {estimate_messages_tokens(messages):,} tokens")

        # Stream response — Live(Text) tránh re-flow markdown lúc stream,
        # transient=True để xóa vùng stream khi xong, rồi render Markdown 1 lần ở cuối.
        text_acc = ""
        tool_calls: list[ToolCall] = []
        finish_reason: str | None = None
        with Live(Text(""), console=console, refresh_per_second=10, transient=True) as live:
            async for event in provider.stream_chat(
                messages=messages,
                tools=tool_schemas if registry.all_tools() else None,
                system_prompt=system_prompt,
            ):
                if event["type"] == "text":
                    text_acc += event["delta"]
                    live.update(Text(text_acc))
                elif event["type"] == "tool_call":
                    tool_calls.append(event["call"])
                elif event["type"] == "finish":
                    finish_reason = event["reason"]
                elif event["type"] == "usage":
                    if cost_tracker is not None:
                        cost_tracker.add(
                            input_tokens=event["input_tokens"],
                            output_tokens=event["output_tokens"],
                        )
                    if context_tracker is not None:
                        context_tracker.update(
                            event["input_tokens"], event["output_tokens"]
                        )

        if text_acc:
            console.print(Markdown(text_acc))

        if finish_reason and finish_reason not in NORMAL_FINISH_REASONS:
            print_info(f"[finish_reason] {finish_reason}")

        if not tool_calls:
            return text_acc

        # Save assistant message with tool_calls
        assistant_msg: dict = {"role": "assistant"}
        if text_acc:
            assistant_msg["text"] = text_acc
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "name": tc.name,
                "args": tc.args,
                "provider_metadata": tc.provider_metadata,
            }
            for tc in tool_calls
        ]
        messages.append(assistant_msg)

        # Execute all tool_calls (batched parallel) then append results
        results = await _execute_tool_calls(
            tool_calls=tool_calls,
            registry=registry,
            context=context,
            permission_checker=permission_checker,
        )
        for tc, result in zip(tool_calls, results):
            formatted = provider.format_tool_result(tc, result)
            if isinstance(formatted, list):
                messages.extend(formatted)
            else:
                messages.append(formatted)


async def _execute_tool_calls(
    tool_calls: list[ToolCall],
    registry: ToolRegistry,
    context: ToolContext,
    permission_checker: PermissionChecker | None,
) -> list:
    """Execute tool_calls với batch partitioning.

    Returns list of ToolResult (success) or string (error/deny),
    same length and order as tool_calls. Mixed types intentional —
    provider.format_tool_result accepts both.
    """
    n = len(tool_calls)
    results: list = [None] * n
    tools: list[Tool | None] = [registry.get(tc.name) for tc in tool_calls]

    # Permission pass (sequential because may prompt user)
    allowed: list[bool] = [True] * n
    for i, (tc, tool) in enumerate(zip(tool_calls, tools)):
        if tool is None:
            print_tool_call(tc.name, tc.args)
            print_tool_error(f"Unknown tool '{tc.name}'")
            results[i] = f"Error: Unknown tool '{tc.name}'"
            allowed[i] = False
            continue
        if permission_checker:
            decision = permission_checker.check(tool, tc.args)
            if decision == PermissionDecision.DENY:
                print_tool_call(tc.name, tc.args)
                if permission_checker.mode.value == "plan":
                    msg = "Permission denied (Plan Mode — read-only only)."
                else:
                    msg = "Permission denied (mode=deny)."
                print_tool_error(msg)
                results[i] = msg
                allowed[i] = False
            elif decision == PermissionDecision.ASK:
                if not permission_checker.prompt_user(tool, tc.args):
                    print_tool_error("Permission denied by user.")
                    results[i] = "Permission denied by user."
                    allowed[i] = False

    # Partition into batches of indices
    batches = _partition_batches(tool_calls, tools, allowed)

    # Execute each batch
    for batch in batches:
        if len(batch) == 1:
            idx = batch[0]
            await _run_sequential(idx, tool_calls[idx], tools[idx], context, results)
        else:
            await _run_parallel(batch, tool_calls, tools, context, results)

    # Fill any None with empty string (shouldn't happen)
    return [r if r is not None else "" for r in results]


def _partition_batches(
    tool_calls: list[ToolCall],
    tools: list[Tool | None],
    allowed: list[bool],
) -> list[list[int]]:
    """Group consecutive read-only+concurrency-safe tools → 1 parallel batch.
    Write/non-safe tools → own batch of 1.
    Skipped (not allowed) tools → not included in any batch.
    """
    batches: list[list[int]] = []
    current: list[int] = []

    for i, (tool, ok) in enumerate(zip(tools, allowed)):
        if not ok or tool is None:
            if current:
                batches.append(current)
                current = []
            continue
        if tool.is_read_only() and tool.is_concurrency_safe():
            current.append(i)
        else:
            if current:
                batches.append(current)
                current = []
            batches.append([i])

    if current:
        batches.append(current)
    return batches


async def _run_sequential(
    idx: int,
    tc: ToolCall,
    tool: Tool,
    context: ToolContext,
    results: list,
) -> None:
    # Interactive tools (e.g. AskUserQuestion) need exclusive terminal control —
    # the Rich Live spinner would clobber prompt_toolkit's rendering.
    if tool.bypasses_spinner():
        t0 = time.time()
        print_tool_call(tc.name, tc.args)
        try:
            result = await tool.execute(tc.args, context)
            preview = str(result)[:80].replace("\n", " ")
            print_tool_result(not result.is_error, time.time() - t0, preview)
            results[idx] = result
        except Exception as e:
            results[idx] = f"Error executing tool: {e}"
            print_tool_error(str(e))
        return

    try:
        async with tool_spinner(tc.name, tc.args) as report:
            result = await tool.execute(tc.args, context)
            preview = str(result)[:80].replace("\n", " ")
            report(success=not result.is_error, preview=preview)
            results[idx] = result
    except Exception as e:
        results[idx] = f"Error executing tool: {e}"
        print_tool_error(str(e))


async def _run_parallel(
    batch: list[int],
    tool_calls: list[ToolCall],
    tools: list[Tool | None],
    context: ToolContext,
    results: list,
) -> None:
    """Run batch of tools in parallel. Print ● calls first, then gather, then ✓ results."""
    console.print(f"  [dim magenta]━ parallel × {len(batch)} ━[/]")
    for idx in batch:
        print_tool_call(tool_calls[idx].name, tool_calls[idx].args)

    async def _one(idx: int) -> tuple[int, ToolResult | Exception, float]:
        t0 = time.time()
        try:
            res = await tools[idx].execute(tool_calls[idx].args, context)
            return idx, res, time.time() - t0
        except Exception as e:
            return idx, e, time.time() - t0

    gathered = await asyncio.gather(*(_one(i) for i in batch))
    by_idx = {idx: (res, dt) for idx, res, dt in gathered}

    for idx in batch:
        res, dt = by_idx[idx]
        if isinstance(res, Exception):
            print_tool_error(f"{tool_calls[idx].name}: {res}")
            results[idx] = f"Error executing tool: {res}"
        else:
            preview = str(res)[:80].replace("\n", " ")
            print_tool_result(not res.is_error, dt, preview)
            results[idx] = res
