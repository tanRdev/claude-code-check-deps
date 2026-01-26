# check-deps

A Claude Code PreToolUse hook that enforces dependency compliance policies. Intercepts package install commands and file writes to block prohibited dependencies before they're introduced into your codebase.

## Why

Package policies matter at scale. Teams standardize on certain libraries for consistency, maintenance, and security. This hook ensures policy compliance automatically—no manual reviews, no missed violations.

## How It Works

The hook integrates with Claude Code's [PreToolUse hook system](https://code.claude.com/docs/en/hooks) to monitor:

- **Package installs**: `npm install`, `pip install`, `yarn add`, `go get`, `pnpm add`, `bun add`, `cargo add`, `poetry add`, `gem install`, `composer require`, and variants
- **Imports in code**: Python (`import X`, `from X import Y`), JavaScript/TypeScript (`import ... from 'X'`, `require()`, dynamic `import()`), Go (`import "X"`)

When a blocked package is detected, the tool execution is blocked with actionable remediation advice.

```
Policy Violation: Blocked dependencies detected

  ✗ "moment": Use date-fns instead (smaller, immutable, tree-shakeable)
  ✗ "requests": Use httpx instead (async support, HTTP/2)

Remove or replace the blocked packages to proceed.
```

Exit codes: `0` (allow), `2` (block), `1` (internal error, fail-open).

## Setup

### 1. Clone into your project

```bash
git clone https://github.com/tanRdev/check-deps.git
```

Or copy the files into your project:

```
your-project/
├── .claude/
│   └── settings.json       # Hook configuration
├── compliance_rules.json   # Your blocked packages
└── hooks/
    └── check_dependencies.py  # The hook script
```

### 2. Configure blocked packages

Edit `compliance_rules.json`:

```json
{
  "blocked_packages": {
    "moment": "Use date-fns instead (smaller, immutable, tree-shakeable)",
    "requests": "Use httpx instead (async support, HTTP/2)",
    "lodash": "Use native ES methods or lodash-es for tree-shaking",
    "jquery": "Use vanilla JS or a modern framework",
    "urllib3": "Use httpx instead",
    "left-pad": "Use String.prototype.padStart()"
  }
}
```

Add or remove entries as your team's standards evolve.

### 3. Wire the hook

Ensure `.claude/settings.json` exists and contains:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 hooks/check_dependencies.py"
          }
        ]
      }
    ]
  }
}
```

The hook script is located at the project root, so this path is relative to your project directory.

### 4. Reload Claude Code

Open your project in Claude Code. The hook will activate automatically for new tool calls.

## Testing

Pipe JSON into the script to verify:

```bash
# Should block (exit 2)
echo '{"tool_name":"Bash","tool_input":{"command":"npm install moment"}}' \
  | python3 hooks/check_dependencies.py

# Should allow (exit 0, no output)
echo '{"tool_name":"Bash","tool_input":{"command":"npm install date-fns"}}' \
  | python3 hooks/check_dependencies.py

# Should block imports in file writes
echo '{"tool_name":"Write","tool_input":{"file_path":"app.py","content":"import requests"}}' \
  | python3 hooks/check_dependencies.py
```

## Features

- **Multi-manager support**: npm, yarn, pnpm, bun, pip, uv, poetry, go, cargo, gem, composer
- **Version-aware parsing**: Handles `moment@2.29.4`, `requests[security]>=2.28`, `@scope/pkg@1.0`
- **Multi-language import detection**: Python, JavaScript/TypeScript, Go
- **Command chain handling**: Processes `&&`, `||`, `;` and piped commands
- **Environment-aware**: Strips `sudo` and env var prefixes
- **Flag-aware**: Ignores flags like `--save`, `-D`, `--global`
- **Config-driven**: Edit `compliance_rules.json` without touching code
- **Fail-open**: Missing or malformed config doesn't block work; warnings logged to stderr
- **Zero dependencies**: Uses stdlib only (works with any Python 3.10+)

## How It Detects Packages

### Bash Commands

Splits on shell operators (`&&`, `||`, `;`, `|`) and matches install subcommands per segment.

```bash
npm install moment && pip install requests  # Detects both
FOO=bar npm install lodash                  # Detects lodash
sudo pip install urllib3                    # Detects urllib3
```

Strips flags (`--save`, `-D`, `--global`, etc.) and version specifiers.

```bash
npm install moment@2.29.4 --save  # Detects "moment", ignores version and flag
```

### File Writes

Scans Python `import` statements, JavaScript `import`/`require()` calls, and Go `import` blocks.

```python
import requests            # Blocked if "requests" in rules
from requests import get   # Blocked (detects top-level "requests")
```

```javascript
import moment from 'moment'   // Blocked
require('moment')             // Blocked
import('moment')              // Blocked (dynamic)
```

```go
import "github.com/user/moment"   // Blocked
import (
  "fmt"
  "github.com/user/moment"
)  // Blocked
```

Relative imports (`./foo`, `../bar`) are always allowed.

## Architecture

- `load_rules()` — Loads and caches `compliance_rules.json` relative to the script
- `extract_packages_from_command()` — Parses Bash commands for install subcommands
- `extract_packages_from_content()` — Detects imports by file extension
- `check_violations()` — Case-insensitive lookup against blocklist
- `format_violation_message()` — Formats actionable error output
- `main()` — Routes stdin JSON by tool type, exits with appropriate code

All functions use standard library only. No external dependencies.

## Limitations & Future Work

- Does not parse `requirements.txt`, `package.json`, `go.mod` files inline (treats `-r requirements.txt` as skip)
- Comment-aware parsing not implemented (false positives on commented-out imports)
- Go module paths match on last segment only (could be extended to full-path matching)
- No support for dynamic package specifications (e.g., environment-based package names)

These are acceptable tradeoffs for v1 — the most common cases are covered.

## License

MIT
