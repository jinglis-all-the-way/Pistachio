import argparse
import cmd2
import importlib
import inspect
import sys
from abc import ABC, abstractmethod

class BasePlugin(ABC):
    """The contract for all plugins."""
    def __init__(self, **kwargs):
        """Plugins can accept arbitrary keyword arguments for configuration."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def commands(self) -> dict:
        pass

    def default(self, statement: str):
        """Optional: A fallback method for commands not handled by the shell."""
        # This is now defined in the base class, so plugins don't have to.
        # The main shell will print the error if no plugin overrides this.
        pass

class TacoShell(cmd2.Cmd):
    """
    A generic, plugin-driven interactive shell framework.
    """
    def __init__(self):
        super().__init__(allow_cli_args=False)
        self.prompt = ">> "
        self.intro = "Taco Interactive Shell. Type 'help' or 'plugin_load <plugin_name>'."
        
        # This will hold the single, active plugin that provides a default handler
        self.active_plugin = None
        self.hidden_commands.extend(['alias', 'macro', 'run_script', 'run_pyscript', 'edit', '_relative_run_script'])

    # --- Plugin Management Commands ---
    
    plugin_parser = argparse.ArgumentParser()
    plugin_parser.add_argument('plugin_name', help='The name of the plugin file to load (e.g., aws_plugin)')
    plugin_parser.add_argument('plugin_args', nargs=argparse.REMAINDER, help='Optional arguments for the plugin (e.g., --mode async)')

    @cmd2.with_argparser(plugin_parser)
    def do_plugin_load(self, args: argparse.Namespace):
        """Loads a plugin and registers its commands and default handler."""
        if self.active_plugin is not None:
            self.poutput(f"A plugin ('{self.active_plugin.name}') is already loaded. Please unload it first.")
            return
            
        try:
            module = importlib.import_module(f"plugins.{args.plugin_name}")
            
            # Find the first class in the module that is a subclass of BasePlugin
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin_class = obj
                    
                    # Parse the key-value arguments for the plugin
                    plugin_kwargs = self._parse_plugin_args(args.plugin_args)
                    
                    # Instantiate the plugin with its specific arguments
                    self.active_plugin = plugin_class(**plugin_kwargs)
                    
                    # Register the plugin's commands and default handler with cmd2
                    self.register_mixin(self.active_plugin)
                    self.default = self.active_plugin.default
                    
                    self.poutput(f"Successfully loaded and registered plugin: '{self.active_plugin.name}'.")
                    return
            
            self.poutput(f"Error: No valid plugin class found in '{args.plugin_name}'.")

        except ImportError:
            self.poutput(f"Error: Plugin '{args.plugin_name}' not found in 'plugins/' directory.")
        except Exception as e:
            self.poutput(f"An unexpected error occurred while loading plugin: {e}")

    def _parse_plugin_args(self, arg_list: list) -> dict:
        """A simple key-value parser for plugin arguments like --key value."""
        kwargs = {}
        i = 0
        while i < len(arg_list):
            if arg_list[i].startswith('--'):
                key = arg_list[i][2:]
                if (i + 1) < len(arg_list) and not arg_list[i+1].startswith('--'):
                    kwargs[key] = arg_list[i+1]
                    i += 2
                else:
                    # It's a flag with no value, treat as True
                    kwargs[key] = True
                    i += 1
            else:
                # Handle positional args if needed in the future
                i += 1
        return kwargs

    def default(self, statement: str):
        """The shell's own default, for when no plugin is loaded."""
        self.poutput(f"Error: Command '{statement.split()[0]}' not found. No default handler plugin is loaded.")

def cli():
    parser = argparse.ArgumentParser(description="An extensible, interactive shell.")
    

    shell = TacoShell()
    sys.exit(shell.cmdloop())

if __name__ == "__main__":
    cli()