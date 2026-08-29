# OpenCode configuration

`install_delivery.py` generates the MCP entry from the installed private
runtime. It validates existing configuration first, backs up the original file,
and changes only `mcp.scientific-figure`; unrelated providers, servers,
commands, agents, tools, and permissions are preserved. The structural editor
understands JSONC line, block, and inline comments plus trailing commas, and
preserves unrelated text byte-for-byte instead of serializing the whole file.
