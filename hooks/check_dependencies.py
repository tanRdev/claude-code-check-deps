#!/usr/bin/env python3
"""Claude Code PreToolUse hook: dependency compliance checker.

Intercepts Bash install commands and file writes to enforce package
policies defined in compliance_rules.json. Blocks tool execution when
a prohibited dependency is detected and provides remediation advice.

Exit codes:
    0 - Allow (no output)
    1 - Internal error (fail-open, non-blocking)
    2 - Block (violation message on stderr)
"""

import json
import re
import shlex
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Install command detection
# ---------------------------------------------------------------------------

CMD_OPS = {"&&", "||", ";", "|"}

# Normalise package name from version/extras specifiers
NPM_PKG_RE = re.compile(r"^(@[^@/]+/[^@/]+|[^@/]+)(?:@.*)?$")
PIP_PKG_RE = re.compile(r"^([a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9])(?:\[.*?\])?(?:[><=!~;].*)?$")
GO_PKG_RE = re.compile(r"^(.+?)(?:@.*)?$")
PIP_SEP_RE = re.compile(r"[-_.]+")

# Flags that consume the next token (skip both flag and value)
PIP_SKIP_NEXT = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable",
                 "-f", "--find-links", "-i", "--index-url", "--extra-index-url",
                 "--target", "-t"}

# ---------------------------------------------------------------------------
# Import detection patterns
# ---------------------------------------------------------------------------

PY_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+([a-zA-Z_]\w*)|from\s+([a-zA-Z_]\w*)\s+import)",
    re.MULTILINE,
)

JS_IMPORT_RE = re.compile(
    r"""(?:"""
    r"""import\s+(?:[\s\S]*?\s+from\s+)?['"]([^'"./][^'"]*)['"]"""
    r"""|require\s*\(\s*['"]([^'"./][^'"]*)['"]"""
    r"""|import\s*\(\s*['"]([^'"./][^'"]*)['"]"""
    r""")""",
)

GO_SINGLE_IMPORT_RE = re.compile(r'import\s+"([^"]+)"')
GO_BLOCK_IMPORT_RE = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
GO_QUOTED_RE = re.compile(r'"([^"]+)"')

JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_rules() -> dict[str, str]:
    config_path = Path(__file__).resolve().parent.parent / "compliance_rules.json"
    try:
        data = json.loads(config_path.read_text())
        return {k.lower(): v for k, v in data.get("blocked_packages", {}).items()}
    except (FileNotFoundError, json.JSONDecodeError, AttributeError) as exc:
        print(f"check_dependencies: config warning: {exc}", file=sys.stderr)
        return {}


def _normalise_npm(token: str) -> str | None:
    m = NPM_PKG_RE.match(token)
    return m.group(1).lower() if m else None


def _normalise_pip(token: str) -> str | None:
    if token in (".", "-e", "--editable"):
        return None
    m = PIP_PKG_RE.match(token)
    if not m:
        return None
    return PIP_SEP_RE.sub("-", m.group(1).lower())


def _normalise_go(token: str) -> list[str]:
    m = GO_PKG_RE.match(token)
    if not m:
        return []
    path = m.group(1)
    parts = path.rstrip("/").split("/")
    names = [parts[-1].lower()]
    if len(parts) > 1:
        names.append(path.lower())
    return names


def _split_command_segments(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&")
    lexer.whitespace_split = True
    tokens = list(lexer)

    segments: list[str] = []
    current: list[str] = []
    for tok in tokens:
        if tok in CMD_OPS:
            if current:
                segments.append(" ".join(current).strip())
                current = []
            continue
        current.append(tok)
    if current:
        segments.append(" ".join(current).strip())
    return segments


def _strip_env_prefix(tokens: list[str]) -> list[str]:
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", tokens[i]):
        i += 1
    return tokens[i:]


def _strip_sudo_prefix(tokens: list[str]) -> list[str]:
    if not tokens or tokens[0] != "sudo":
        return tokens
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 1
    return tokens[i:]


def _basename(token: str) -> str:
    return Path(token).name


def _parse_install_invocation(tokens: list[str]) -> tuple[str, list[str]] | None:
    if not tokens:
        return None

    cmd = _basename(tokens[0])
    rest = tokens[1:]

    if cmd in {"npm", "npx"} and rest and rest[0] in {"install", "i", "add"}:
        return "npm", rest[1:]
    if cmd == "yarn" and rest and rest[0] in {"add", "install"}:
        return "npm", rest[1:]
    if cmd == "pnpm" and rest and rest[0] in {"add", "install", "i"}:
        return "npm", rest[1:]
    if cmd == "bun" and rest and rest[0] in {"add", "install", "i"}:
        return "npm", rest[1:]

    if cmd in {"pip", "pip3", "pipx"} and rest and rest[0] == "install":
        return "pip", rest[1:]
    if cmd == "uv" and rest:
        if rest[0] == "add":
            return "pip", rest[1:]
        if len(rest) >= 2 and rest[0] == "pip" and rest[1] == "install":
            return "pip", rest[2:]
    if cmd == "poetry" and rest and rest[0] == "add":
        return "pip", rest[1:]
    if cmd.startswith("python") and len(rest) >= 3 and rest[0] == "-m" and rest[1] == "pip" and rest[2] == "install":
        return "pip", rest[3:]

    if cmd == "go" and rest and rest[0] in {"get", "install"}:
        return "go", rest[1:]
    if cmd == "cargo" and rest and rest[0] == "add":
        return "npm", rest[1:]
    if cmd == "gem" and rest and rest[0] == "install":
        return "npm", rest[1:]
    if cmd == "composer" and rest and rest[0] == "require":
        return "npm", rest[1:]

    return None


def extract_packages_from_command(command: str) -> list[str]:
    packages: list[str] = []
    segments = _split_command_segments(command)
    for segment in segments:
        if not segment:
            continue
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            continue

        tokens = _strip_sudo_prefix(_strip_env_prefix(tokens))
        invocation = _parse_install_invocation(tokens)
        if not invocation:
            continue

        manager, args = invocation

        skip_next = False
        for tok in args:
            if skip_next:
                skip_next = False
                continue
            if tok.startswith("-"):
                if manager == "pip" and tok in PIP_SKIP_NEXT:
                    skip_next = True
                continue

            if manager == "npm":
                name = _normalise_npm(tok)
                if name:
                    packages.append(name)
            elif manager == "pip":
                name = _normalise_pip(tok)
                if name:
                    packages.append(name)
            elif manager == "go":
                packages.extend(_normalise_go(tok))

    return packages


def _strip_python_comments(content: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", content)


def _strip_c_style_comments(content: str) -> str:
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", content)


def extract_packages_from_content(content: str, file_path: str) -> list[str]:
    ext = Path(file_path).suffix.lower()
    packages: list[str] = []

    if ext == ".py":
        for m in PY_IMPORT_RE.finditer(_strip_python_comments(content)):
            name = (m.group(1) or m.group(2)).lower()
            packages.append(name)

    elif ext in JS_EXTENSIONS:
        for m in JS_IMPORT_RE.finditer(_strip_c_style_comments(content)):
            raw = m.group(1) or m.group(2) or m.group(3)
            # @scope/pkg/subpath -> @scope/pkg
            if raw.startswith("@"):
                parts = raw.split("/")
                name = "/".join(parts[:2]).lower()
            else:
                name = raw.split("/")[0].lower()
            packages.append(name)

    elif ext == ".go":
        content_wo_comments = _strip_c_style_comments(content)
        for m in GO_SINGLE_IMPORT_RE.finditer(content_wo_comments):
            packages.extend(_normalise_go(m.group(1)))
        for block in GO_BLOCK_IMPORT_RE.finditer(content_wo_comments):
            for m in GO_QUOTED_RE.finditer(block.group(1)):
                packages.extend(_normalise_go(m.group(1)))

    return packages


def check_violations(
    packages: list[str], rules: dict[str, str]
) -> list[tuple[str, str]]:
    seen: set[str] = set()
    violations: list[tuple[str, str]] = []
    for pkg in packages:
        key = pkg.lower()
        if key in rules and key not in seen:
            seen.add(key)
            violations.append((pkg, rules[key]))
    return violations


def format_violation_message(violations: list[tuple[str, str]]) -> str:
    lines = ["", "Policy Violation: Blocked dependencies detected", ""]
    for pkg, advice in violations:
        lines.append(f'  ✗ "{pkg}": {advice}')
    lines.append("")
    lines.append("Remove or replace the blocked packages to proceed.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"check_dependencies: invalid input: {exc}", file=sys.stderr)
        sys.exit(1)

    rules = load_rules()
    if not rules:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    packages: list[str] = []

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            packages = extract_packages_from_command(command)

    elif tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "") or tool_input.get("new_string", "")
        if content and file_path:
            packages = extract_packages_from_content(content, file_path)
    else:
        sys.exit(0)

    if not packages:
        sys.exit(0)

    violations = check_violations(packages, rules)
    if not violations:
        sys.exit(0)

    print(format_violation_message(violations), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
