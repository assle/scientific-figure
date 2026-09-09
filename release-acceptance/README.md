# Release acceptance evidence

`scripts/release.py --publish` requires `X.Y.Z.json` for the Target version.
Record it only after installing the candidate Product bundle, completely
restarting Codex, opening a new task, and observing the Native plugin, Active
runtime, CLI, and MCP at the same Product version with no old processes.

The file contains no credentials, Provider configuration, prompts, or user data:

```json
{
  "product_version": "0.6.0",
  "codex_restart_verified": true,
  "new_task_mcp_verified": true,
  "plugin_version": "0.6.0",
  "active_runtime_version": "0.6.0",
  "cli_version": "0.6.0",
  "mcp_version": "0.6.0",
  "configuration_app_version": "0.6.0",
  "old_processes": 0
}
```

Do not copy the example into a versioned evidence file without performing the
observations. Missing evidence intentionally blocks tag creation.
