# REDkit local MCP server

This stdio server exposes the installed REDkit depot to Codex. It can check the
installation, list files in a depot folder, inspect printable strings in a
binary asset, copy one asset into `witcher3-romance-mod/depot/`, and compare a
checkout with its installed original.

The server is registered globally in Codex as `witcher3_redkit`. The workspace's
`.codex/config.toml` also records the same configuration for trusted project
sessions. Start a new Codex session after changing MCP configuration, then
check `codex mcp get witcher3_redkit`.

The server never writes to the REDkit or game installation. CR2W files require
REDkit for structured scene editing; printable strings are only search clues.
The installed `editor.exe` is a Windows GUI program, and this server does not
automate its interface or validate a mod in game.

Runtime: Python 3.13, using the standard library for stdio MCP transport.
