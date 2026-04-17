# TacoShell Project Guidelines

# TacoShell Project Guidelines

## Architecture

TacoShell is an extensible, plugin-based interactive shell built on `cmd2`. It separates concerns into:

- **Shell layer** (`TacoShell.py`): Interactive command dispatcher with plugin management
- **Plugin interface** (`plugin_interface.py`): Contract all plugins must follow
- **Business logic** (`lib/`): Reusable components (currently AWS-focused: instances, commands, snapshots)
- **Plugin implementations** (`plugins/`): Specific functionality (currently AWS: ADCM command manager, snapshots)

Plugins are loaded dynamically at runtime without restarting. Only one plugin can be the "default handler" for unrecognized commands. The architecture is flexible for any domain, not limited to AWS.

## Build and Test

- **Install**: `pip install -e .` (installs `taco` command)
- **Run**: `python TacoShell.py` or `taco` (if installed)
- **Load plugin**: `taco ADCM` (at startup) or `shell> plugin_load ADCM` (interactive)
- **Test plugin loading**: Run shell and use `plugin_load <name>` to verify plugins load without errors
- **Dependencies**: `cmd2`, `boto3`, `aioboto3` (add to pyproject.toml if missing)

No test infrastructure configured yet. Test plugins by loading them in the shell.

## Code Style

Follow Python conventions. Reference `plugins/ADCM.py` for plugin template pattern. Use `do_*` methods for commands in plugins.

## Conventions

- **Plugin loading**: Plugins are cmd2 mixins inheriting `BasePlugin` with `name` property
- **Instance resolution**: By ID (`i-0abc...`) or Name tag (exact match on running instances); must be SSM-ready
- **Command execution**: Sync (blocking) vs async (parallel via `asyncio.gather()`)
- **AWS prerequisites**: Boto3 configured, instances running with SSM agent online, IAM permissions for SSM

Fix common issues: Add missing `import cmd2` in ADCM plugins, fix imports in snapshot_manager_plugin.py (`webshell` → `plugin_interface`).