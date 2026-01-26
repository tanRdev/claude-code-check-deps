# check-deps

Claude Code PreToolUse hook that blocks prohibited dependencies before they hit your codebase. Intercepts `npm install`, `pip install`, `yarn add`, `go get`, etc., plus imports in Python/JS/TS/Go files.

## Installation

Copy these files to your project:

```
your-project/
├── .claude/
│   └── settings.json
├── compliance_rules.json
└── hooks/
    └── check_dependencies.py
```

Get them from GitHub:

```bash
git clone https://github.com/tanRdev/check-deps.git
# Copy the three files above to your project
```

Or use the prompt below with your LLM/CLI tool.

## Quick Start

**1. Add hook wiring** to `.claude/settings.json`:

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

**2. Configure blocked packages** in `compliance_rules.json`:

```json
{
  "blocked_packages": {
    "moment": "Use date-fns instead",
    "requests": "Use httpx instead",
    "lodash": "Use native ES or lodash-es"
  }
}
```

**3. Reload Claude Code.** Done.

When blocked packages are detected:

```
Policy Violation: Blocked dependencies detected

  ✗ "moment": Use date-fns instead
  ✗ "requests": Use httpx instead

Remove or replace the blocked packages to proceed.
```

## Installation Prompt

Copy and paste this into your LLM/agentic CLI to install the hook:

```
Install the check-deps Claude Code hook into my project.

1. Create the file structure:
   - .claude/settings.json (PreToolUse hook configuration)
   - compliance_rules.json (blocked packages config)
   - hooks/check_dependencies.py (the hook script)

2. For .claude/settings.json: Wire up the PreToolUse hook to match "Bash|Write|Edit" and run "python3 hooks/check_dependencies.py"

3. For compliance_rules.json: Start with blocked_packages for "moment" (use date-fns), "requests" (use httpx), "lodash" (use native or lodash-es), and "urllib3" (use httpx)

4. For hooks/check_dependencies.py: A Python3 hook that intercepts package installs and imports. It supports:
   - 13 package managers (npm, yarn, pnpm, bun, pip, uv, poetry, go, cargo, gem, composer)
   - Import detection in Python, JS/TS, Go
   - Version specifiers (moment@2.29.4, requests>=2.28)
   - Chained commands (npm install foo && pip install bar)
   - Sudo and env var prefixes
   - Relative imports are always allowed

The script should read JSON from stdin with tool_name and tool_input, extract packages, check against compliance_rules.json, and exit with code 0 (allow), 2 (block with error), or 1 (internal error).
```

## How It Works

**Bash commands**: Splits on `&&`, `||`, `;`, `|`. Detects install managers and extracts package names, stripping flags and version specifiers.

```bash
npm install moment@2.29.4 --save  # Detects "moment"
sudo pip install requests         # Detects "requests"
npm install foo && pip install bar  # Detects both
```

**File writes**: Scans imports by file extension.

```python
import requests            # Blocked
from requests import get   # Blocked (top-level package)
```

```javascript
import moment from 'moment'   // Blocked
require('moment')             // Blocked
import('moment')              // Blocked
```

```go
import "github.com/user/moment"  // Blocked
```

Relative imports (`./foo`, `../bar`) are always allowed.

## Features

- **13 package managers**: npm, yarn, pnpm, bun, pip, uv, poetry, go, cargo, gem, composer
- **Multi-language**: Python, JS/TS, Go imports
- **Smart parsing**: Version specifiers, scoped packages, flags, sudo/env prefixes, command chains
- **Config-driven**: Edit `compliance_rules.json`, no code changes
- **Fail-open**: Missing/malformed config doesn't block; warnings to stderr
- **Zero deps**: Stdlib only, Python 3.10+

## Testing

```bash
# Block (exit 2)
echo '{"tool_name":"Bash","tool_input":{"command":"npm install moment"}}' | python3 hooks/check_dependencies.py

# Allow (exit 0)
echo '{"tool_name":"Bash","tool_input":{"command":"npm install date-fns"}}' | python3 hooks/check_dependencies.py

# Block imports
echo '{"tool_name":"Write","tool_input":{"file_path":"app.py","content":"import requests"}}' | python3 hooks/check_dependencies.py
```

## Known Limitations

- Doesn't parse `requirements.txt`, `package.json`, `go.mod` inline (skips `-r requirements.txt`)
- No comment-aware parsing (could false-positive on commented imports)
- Go paths match last segment only
- No dynamic package specs

## License

MIT
