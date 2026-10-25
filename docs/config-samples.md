# Client configuration samples

Replace `/path/to/images` with the one folder the server may read. No secrets are needed: the server uses no API keys.

## Claude Code (desktop or Termux)

```sh
claude mcp add imagetoolbox -- imagetoolbox-mcp --root /path/to/images
# optional: separate output folder and process isolation
claude mcp add imagetoolbox -- imagetoolbox-mcp --root /path/to/images --out /path/to/out --isolate 120
```

## Claude Desktop, Cursor, Windsurf and other `mcpServers` clients

```json
{
  "mcpServers": {
    "imagetoolbox": {
      "command": "imagetoolbox-mcp",
      "args": ["--root", "/path/to/images"]
    }
  }
}
```

Windows: use `"C:\\Users\\you\\Pictures"` (escaped backslashes) or forward slashes.

## VS Code (`.vscode/mcp.json`)

```json
{
  "servers": {
    "imagetoolbox": {
      "type": "stdio",
      "command": "imagetoolbox-mcp",
      "args": ["--root", "${workspaceFolder}/images"]
    }
  }
}
```

## Gemini CLI (`~/.gemini/settings.json`)

```json
{
  "mcpServers": {
    "imagetoolbox": {
      "command": "imagetoolbox-mcp",
      "args": ["--root", "/data/data/com.termux/files/home/storage/pictures"],
      "timeout": 120000
    }
  }
}
```

## Environment variables instead of arguments

| Variable | Same as |
| --- | --- |
| `IMAGETOOLBOX_MCP_ROOT` | `--root` |
| `IMAGETOOLBOX_MCP_OUT` | `--out` |
| `IMAGETOOLBOX_MCP_ISOLATE` | `--isolate SECONDS` |

## Client-specific limits found so far

- Tool names use `snake_case` because some model APIs reject dots.
- `image_batch` `options` is a free-form object (validated by the server) because some clients handle JSON-schema unions badly (ADR-0004).
- Progress notifications are sent after each batch file; clients that ignore progress still get the final result.
- Large batches can exceed a client's default tool timeout (Gemini CLI: raise `timeout`; Claude Code: `MCP_TOOL_TIMEOUT`).
