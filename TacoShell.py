import argparse
import cmd2
from cmd2 import CommandSet, with_default_category
import importlib
import inspect
import sys
import pkgutil
from typing import Optional, Dict, List, Union

@with_default_category('plugin')
class PluginCommandSet(CommandSet):
    def __init__(self):
        # --- State for managing multiple plugins ---
        self.loaded_plugins: Dict[str] = {} 
        self.default_handler_plugin: Optional[str] = None

        

        super().__init__()

    plugin_parser = cmd2.Cmd2ArgumentParser()
    plugin_parser.add_argument('plugin_name', help='The name of the plugin file to load (e.g., aws_plugin)')
    plugin_parser.add_argument('plugin_args', nargs=argparse.REMAINDER, help='Optional arguments for the plugin (e.g., --mode async)')

    def do_load(self, plugin_name: cmd2.Statement):
        """Internal method to load a plugin. Used by both CLI and startup."""
        if plugin_name in self.loaded_plugins:
            self.poutput(f"Error: Plugin '{plugin_name}' is already loaded.")
            return
            
        try:
            self.poutput(f"Attempting to import module: 'plugins.{plugin_name}'...")
            module = importlib.import_module(f"plugins.{plugin_name}")
            
            for _, obj in inspect.getmembers(module, inspect.isclass):
                plugin_class = obj
                
                plugin_kwargs = self._parse_plugin_args(plugin_args)
                plugin_instance = plugin_class(**plugin_kwargs)
                
                # Give the plugin a reference back to the shell
                if hasattr(plugin_instance, 'set_shell'):
                    plugin_instance.set_shell(self)
                
                # Check if this plugin wants to be the default handler
                is_default_handler = plugin_instance.default
                if is_default_handler and self.default_handler_plugin is not None:
                    self.poutput(f"Error: Cannot load '{plugin_instance.name}' because another plugin ('{self.default_handler_plugin}') has already registered a default command handler.")
                    return

                # Register commands by copying do_* methods to shell instance
                for method_name in dir(plugin_instance):
                    if method_name.startswith('do_'):
                        method = getattr(plugin_instance, method_name)
                        if callable(method):
                            setattr(self, method_name, method)
                
                self.loaded_plugins[plugin_instance.name] = plugin_instance
                self.poutput(f"Successfully loaded plugin '{plugin_instance.name}'.")

                # If it's a default handler, register it
                if is_default_handler:
                    self.default = plugin_instance.default
                    self.default_handler_plugin = plugin_instance.name
                    self.poutput(f"Plugin '{plugin_instance.name}' has registered as the default command handler.")
                return # Exit after successful load
    
        except Exception as e:
            # --- CATCH-ALL EXCEPTION FOR MAXIMUM DIAGNOSIS ---
            import traceback
            self.poutput("\n" + "="*60)
            self.poutput("--- AN UNEXPECTED AND CRITICAL ERROR OCCURRED DURING PLUGIN LOAD ---")
            self.poutput(f"Python Exception Type: {type(e).__name__}")
            self.poutput(f"Python Error Message: {e}")
            self.poutput("\n--- FULL TRACEBACK ---")
            # This prints the full, detailed error stack trace
            self.poutput(traceback.format_exc())
            self.poutput("="*60 + "\n")

    @cmd2.with_argparser(plugin_parser)
    def do_plugin_load(self, args: argparse.Namespace):
        """Loads a plugin and prints detailed error information on failure."""
        self._load_plugin(args.plugin_name, args.plugin_args)

    unload_parser = argparse.ArgumentParser()
    unload_parser.add_argument('plugin_name', help='The name of the plugin to unload.')

    @cmd2.with_argparser(unload_parser)
    def do_plugin_unload(self, args: argparse.Namespace):
        """Unloads a plugin, removing its commands and default handler."""
        if args.plugin_name not in self.loaded_plugins:
            self.poutput(f"Error: Plugin '{args.plugin_name}' is not currently loaded.")
            return

        plugin_instance = self.loaded_plugins[args.plugin_name]
        
        # Remove the plugin's do_* methods from the shell instance
        for method_name in dir(plugin_instance):
            if method_name.startswith('do_'):
                if hasattr(self, method_name):
                    delattr(self, method_name)
        
        # If this plugin was the default handler, reset the shell's default
        if self.default_handler_plugin == args.plugin_name:
            self.default = self.__class__.default.__get__(self, self.__class__)
            self.default_handler_plugin = None
            self.poutput(f"Unregistered default command handler from plugin '{args.plugin_name}'.")

        del self.loaded_plugins[args.plugin_name]
        self.poutput(f"Plugin '{args.plugin_name}' unloaded successfully.")

    def do_plugin_list(self, _: cmd2.Statement):
        """Lists available plugins in the 'plugins' directory and shows which are loaded."""
        self.poutput("\n--- Loaded Plugins ---")
        if not self.loaded_plugins:
            self.poutput("  No plugins are currently loaded.")
        else:
            for name in sorted(self.loaded_plugins.keys()):
                self.poutput(f"  - {name}")

        self.poutput("\n--- Available Plugins ---")
        try:
            # Use pkgutil to find all modules in the 'plugins' package
            available = [name for _, name, _ in pkgutil.iter_modules(['plugins'])]
            if not available:
                self.poutput("  No plugins found in the 'plugins' directory.")
            else:
                for name in sorted(available):
                    status = "(loaded)" if name in self.loaded_plugins else ""
                    self.poutput(f"  - {name} {status}")
        except ImportError:
            self.poutput("  Error: 'plugins' directory not found or is not a valid package (missing __init__.py?).")
    
    def _parse_plugin_args(self, arg_list: List[str]) -> Dict[str, Union[str, bool]]:
        """A simple key-value parser for plugin arguments like --key value."""
        kwargs: Dict[str, Union[str, bool]] = {}
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

class TacoShell(cmd2.Cmd):
    """A generic, multi-plugin interactive shell framework powered by cmd2."""
    
    def __init__(self, plugin_args: Optional[argparse.Namespace] = None):
        super().__init__(allow_cli_args=False, auto_load_commands=True)
        self.prompt = ">> "
        self.intro = "Taco Shell Framework. Type 'help' or 'plugin_load <plugin_name>'."
        
        # Hide built-in cmd2 commands we don't need
        self.hidden_commands.extend(['run_script', 'run_pyscript', '_relative_run_script'])
        
        # If plugin arguments were passed at startup, load the plugin immediately
        if plugin_args and plugin_args.plugin_name:
            self._load_plugin(plugin_args.plugin_name, plugin_args.plugin_args)
        

    # --- Plugin Management Commands ---
    
    plugin_parser = argparse.ArgumentParser()
    plugin_parser.add_argument('plugin_name', help='The name of the plugin file to load (e.g., aws_plugin)')
    plugin_parser.add_argument('plugin_args', nargs=argparse.REMAINDER, help='Optional arguments for the plugin (e.g., --mode async)')

    

        

    def default(self, statement: cmd2.Statement) -> Union[bool, None]:
        """The shell's own default handler, for when no plugin is loaded."""
        self.poutput(f"Error: Command '{statement.command}' not found. No default handler plugin is loaded.")
        return False

def cli():
    parser = argparse.ArgumentParser(description="An extensible, interactive shell framework.")
    parser.add_argument('plugin_name', nargs='?', help='Optional: The name of a plugin to load on startup.')
    parser.add_argument('plugin_args', nargs=argparse.REMAINDER, help='Optional arguments for the plugin.')
    
    # We use parse_known_args to separate cmd2's args from our own
    args, _ = parser.parse_known_args()
    shell = TacoShell(plugin_args=args)
    sys.exit(shell.cmdloop())

if __name__ == "__main__":
    cli()
