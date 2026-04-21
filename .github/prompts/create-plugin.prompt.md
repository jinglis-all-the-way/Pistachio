---
name: create-plugin
description: Create a new TacoShell plugin following the BasePlugin interface. Use when: adding new functionality to the shell, implementing domain-specific commands, creating default handlers for unrecognized commands.
---

# Create Plugin Prompt

Generate a new TacoShell plugin that follows the established patterns.

## Requirements

- Plugin name: {plugin_name}
- Purpose: {brief_description}
- Commands to implement: {list_of_commands}
- Default handler needed: {yes/no}

## Structure

Create a new file in `plugins/{plugin_name}.py` with:

1. Import necessary modules (BasePlugin, cmd2 if using decorators)
2. Define plugin class inheriting BasePlugin
3. Implement `name` property
4. Implement `commands` property (dict of command functions)
5. Use `do_*` methods for cmd2 commands
6. Optional: implement `default()` method for unrecognized commands

## Example

```python
from plugin_interface import BasePlugin
import cmd2

class MyPlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "my_plugin"
    
    @property
    def commands(self) -> dict:
        return {
            'my_command': self.do_my_command,
        }
    
    def do_my_command(self, args):
        """Handle my_command"""
        self.poutput("My command executed")
    
    def default(self, statement):
        """Optional: handle unrecognized commands"""
        self.poutput(f"Unrecognized: {statement}")
```

## Validation

After creation:
- Test loading: `plugin_load {plugin_name}`
- Verify commands appear in help
- Test command execution