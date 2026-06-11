import asyncio
import os
import sys

from kagent.config import (
    LLM_PROVIDER,
    get_model,
    get_api_key,
    OPENAI_BASE_URL,
    OPENAI_VERIFY_SSL,
)
from kagent.providers.gemini import GeminiProvider
from kagent.providers.openai_compat import OpenAIProvider
from kagent.providers.retry import set_retry_notifier
from kagent.tools import create_default_registry as create_tool_registry
from kagent.engine import agent_loop
from kagent.permissions import PermissionChecker, PermissionMode
from kagent.conversation import (
    CostTracker,
    new_session_id,
    save_session,
    load_session,
)
from kagent.memory import MemoryManager
from kagent.commands import (
    CommandContext,
    create_default_registry as create_command_registry,
    parse_slash,
)
from kagent.ui.terminal import console, print_welcome, print_error, print_info, get_prompt_label


def create_provider():
    api_key = get_api_key()
    model = get_model()
    if LLM_PROVIDER == "gemini":
        return GeminiProvider(api_key=api_key, model=model)
    if LLM_PROVIDER == "openai":
        return OpenAIProvider(
            api_key=api_key,
            model=model,
            base_url=OPENAI_BASE_URL or None,
            verify_ssl=OPENAI_VERIFY_SSL,
        )
    raise ValueError(f"Unknown provider: {LLM_PROVIDER}")


def parse_permission_mode() -> PermissionMode:
    for arg in sys.argv[1:]:
        if arg == "--auto":
            return PermissionMode.AUTO
        if arg == "--deny":
            return PermissionMode.DENY
        if arg == "--plan":
            return PermissionMode.PLAN
        if arg in ("--accept-edits", "--accept"):
            return PermissionMode.ACCEPT_EDITS
    return PermissionMode.DEFAULT


def parse_resume_id() -> str | None:
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--resume" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--resume="):
            return arg.split("=", 1)[1]
    return None


def _print_retry(attempt: int, max_retries: int, exc: BaseException, delay: float) -> None:
    print_info(
        f"  [retry {attempt + 1}/{max_retries}] {type(exc).__name__}: {exc} — chờ {delay:.1f}s"
    )


async def main():
    # Composition root: inject UI callback cho retry layer (provider layer không import UI).
    set_retry_notifier(_print_retry)

    provider = create_provider()
    model = get_model()

    perm_mode = parse_permission_mode()
    permission_checker = PermissionChecker(mode=perm_mode)
    tool_registry = create_tool_registry(
        provider=provider,
        permission_checker=permission_checker,
    )
    cmd_registry = create_command_registry()

    cost_tracker = CostTracker(model=model)
    memory = MemoryManager()

    messages: list[dict] = []

    resume_id = parse_resume_id()
    if resume_id:
        loaded = load_session(resume_id)
        if loaded:
            messages = loaded
            session_id = resume_id
            console.print(f"[green]Resumed session:[/] {resume_id} ({len(loaded)} messages)")
        else:
            console.print(f"[red]Session not found:[/] {resume_id} — starting new")
            session_id = new_session_id()
    else:
        session_id = new_session_id()

    session_id_ref = [session_id]

    cmd_ctx = CommandContext(
        messages=messages,
        session_id_ref=session_id_ref,
        cost_tracker=cost_tracker,
        provider=provider,
        tool_registry=tool_registry,
        model=model,
        provider_name=LLM_PROVIDER,
        memory=memory,
        permission_checker=permission_checker,
    )

    print_welcome(
        provider=LLM_PROVIDER,
        model=model,
        tools=[t.name for t in tool_registry.all_tools()],
        cwd=os.getcwd(),
        perm_mode=perm_mode.value,
    )
    console.print(f"[dim]Session: {session_id_ref[0]}  |  type /help for commands[/]\n")

    while True:
        try:
            label = get_prompt_label(permission_checker.mode)
            user_input = console.input(label + " ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye![/]")
            break

        stripped = user_input.strip()
        if not stripped:
            continue

        parsed = parse_slash(stripped)
        if parsed is not None:
            name, args = parsed
            cmd = cmd_registry.get(name)
            if cmd is None:
                console.print(f"[red]Unknown command:[/] /{name}  (try [cyan]/help[/])")
                continue
            try:
                await cmd.execute(args, cmd_ctx)
            except SystemExit:
                raise
            except Exception as e:
                print_error(f"Command /{name} failed: {e}")
            continue

        if stripped.lower() in ("exit", "quit"):
            console.print("[dim]Bye![/]")
            break

        messages.append({"role": "user", "content": stripped})

        try:
            response_text = await agent_loop(
                messages=messages,
                provider=provider,
                registry=tool_registry,
                permission_checker=permission_checker,
                cost_tracker=cost_tracker,
                model=model,
            )
            messages.append({"role": "assistant", "content": response_text})
            save_session(
                session_id_ref[0],
                messages,
                metadata={"model": model, "provider": LLM_PROVIDER},
            )
            console.print()
        except Exception as e:
            print_error(str(e))
            if messages and messages[-1].get("role") == "user":
                messages.pop()


def main_sync() -> None:
    """Sync entry point for [project.scripts] — pyproject can't call async directly."""
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        from kagent.setup_wizard import run_init_wizard
        sys.exit(run_init_wizard())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main_sync()
