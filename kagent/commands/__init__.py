from kagent.commands.base import Command, CommandContext, CommandRegistry, parse_slash
from kagent.commands.builtin import (
    HelpCommand,
    CostCommand,
    TokensCommand,
    MicroCompactCommand,
    CompactCommand,
    ClearCommand,
    SessionsCommand,
    ResumeCommand,
    NewSessionCommand,
    SaveCommand,
    ExitCommand,
    QuitCommand,
)
from kagent.commands.git import DiffCommand, CommitCommand, ReviewCommand
from kagent.commands.memory import RememberCommand, MemoryCommand, ForgetCommand
from kagent.commands.todo import TodosCommand
from kagent.commands.plan import PlanCommand
from kagent.commands.mode import ModeCommand


def create_default_registry() -> CommandRegistry:
    """Build registry với tất cả built-in commands.

    HelpCommand cần tham chiếu chính registry → register sau cùng.
    """
    reg = CommandRegistry()

    # Session + history
    reg.register(CostCommand())
    reg.register(TokensCommand())
    reg.register(MicroCompactCommand())
    reg.register(CompactCommand())
    reg.register(ClearCommand())
    reg.register(SessionsCommand())
    reg.register(ResumeCommand())
    reg.register(NewSessionCommand())
    reg.register(SaveCommand())

    # Git
    reg.register(DiffCommand())
    reg.register(CommitCommand())
    reg.register(ReviewCommand())

    # Memory
    reg.register(RememberCommand())
    reg.register(MemoryCommand())
    reg.register(ForgetCommand())

    # Todos
    reg.register(TodosCommand())

    # Plan Mode
    reg.register(PlanCommand())
    reg.register(ModeCommand())

    # Exit
    reg.register(ExitCommand())
    reg.register(QuitCommand())

    # Help — needs reg reference
    reg.register(HelpCommand(registry=reg))

    return reg
