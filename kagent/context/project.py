import os
import subprocess


def get_project_context(cwd: str) -> str:
    """Detect project type, git info, and environment.

    Claude Code equivalent: context.ts → getSystemContext()
    """
    parts = []

    # Git info — dùng `git rev-parse` thay vì check .git trực tiếp
    # vì cwd có thể là subdirectory của git repo
    is_git = _run_quiet("git rev-parse --is-inside-work-tree", cwd) == "true"
    if is_git:
        parts.append("This is a git repository.")
        branch = _run_quiet("git branch --show-current", cwd)
        if branch:
            parts.append(f"Current branch: {branch}")
        status = _run_quiet("git status --short", cwd)
        if status:
            parts.append(f"Git status:\n{status}")
        commits = _run_quiet("git log --oneline -5", cwd)
        if commits:
            parts.append(f"Recent commits:\n{commits}")
    else:
        parts.append("This is NOT a git repository.")

    # Detect project type
    detections = {
        "package.json": "Node.js/JavaScript project",
        "requirements.txt": "Python project (requirements.txt)",
        "pyproject.toml": "Python project (pyproject.toml)",
        "Cargo.toml": "Rust project",
        "go.mod": "Go project",
        "pom.xml": "Java/Maven project",
        "build.gradle": "Java/Gradle project",
    }
    for file, description in detections.items():
        if os.path.exists(os.path.join(cwd, file)):
            parts.append(f"Project type: {description}")
            break

    return "\n".join(parts)


def _run_quiet(cmd: str, cwd: str) -> str:
    """Run command, return stdout or empty string."""
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""
