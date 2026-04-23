"""Plugin management system for TacoShell."""
import importlib
import cmd2
import inspect
import pkgutil
import sys
import traceback
from typing import Dict, List, Union, Optional, Any, Type

from plugin_interface import BasePlugin


class PluginManager:
    """Manages dynamic plugin loading, unloading, and default handlers."""
    
    def __init__(self, shell: Any):
        """Initialize the plugin manager."""
        self.shell = shell
        self.loaded_plugins: Dict[str, BasePlugin] = {}
        self.default_handler_plugin: Optional[str] = None
    
    def load(self, plugin_name: str, plugin_args: Optional[List[str]] = None) -> bool:
        """Load a plugin by name. Returns True on success, False on failure."""
        if plugin_name in self.loaded_plugins:
            self.shell.poutput(f"Error: Plugin '{plugin_name}' is already loaded.")
            return False
        
        try:
            self.shell.poutput(f"Attempting to import module: 'plugins.{plugin_name}'...")
            
            # Ensure the script directory is in path
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            
            module = importlib.import_module(f"plugins.{plugin_name}")
            
            # Find the plugin class in the module
            plugin_class = self._find_plugin_class(module)
            if not plugin_class:
                self.shell.poutput(f"Error: No valid plugin class found in '{plugin_name}'.")
                return False
            
            # Parse arguments and instantiate
            kwargs = self._parse_plugin_args(plugin_args or [])
            plugin_instance = plugin_class(**kwargs)
            
            # Give the plugin a reference back to the shell
            if hasattr(plugin_instance, 'set_shell'):
                plugin_instance.set_shell(self.shell)
            
            # Check for default handler conflict
            has_default_handler = self._has_default_handler(plugin_instance)
            if has_default_handler and self.default_handler_plugin is not None:
                self.shell.poutput(
                    f"Error: Cannot load '{plugin_instance.name}' because another plugin "
                    f"('{self.default_handler_plugin}') has already registered a default handler."
                )
                return False
            
            # Register the plugin's commands
            self._register_commands(plugin_instance)
            
            # Store the plugin
            self.loaded_plugins[plugin_instance.name] = plugin_instance
            self.shell.poutput(f"Successfully loaded plugin '{plugin_instance.name}'.")
            
            # Register default handler if applicable
            if has_default_handler:
                self.shell.default = plugin_instance.default
                self.default_handler_plugin = plugin_instance.name
                self.shell.poutput(f"Plugin '{plugin_instance.name}' registered as default handler.")
            
            return True
            
        except Exception as e:
            self._print_error(f"Error loading plugin '{plugin_name}'", e)
            return False
    
    def unload(self, plugin_name: str) -> bool:
        """Unload a plugin by name. Returns True on success."""
        if plugin_name not in self.loaded_plugins:
            self.shell.poutput(f"Error: Plugin '{plugin_name}' is not loaded.")
            return False
        
        try:
            plugin_instance = self.loaded_plugins[plugin_name]
            
            # Unregister the plugin's commands
            self._unregister_commands(plugin_instance)
            
            # Reset default handler if applicable
            if self.default_handler_plugin == plugin_name:
                self.shell.default = self.shell.__class__.default
                self.default_handler_plugin = None
                self.shell.poutput(f"Unregistered default handler from plugin '{plugin_name}'.")
            
            del self.loaded_plugins[plugin_name]
            self.shell.poutput(f"Plugin '{plugin_name}' unloaded successfully.")
            return True
            
        except Exception as e:
            self._print_error(f"Error unloading plugin '{plugin_name}'", e)
            return False
    
    def list_plugins(self) -> None:
        """Display loaded and available plugins."""
        self.shell.poutput("\n--- Loaded Plugins ---")
        if not self.loaded_plugins:
            self.shell.poutput("  No plugins are currently loaded.")
        else:
            for name in sorted(self.loaded_plugins.keys()):
                self.shell.poutput(f"  - {name}")
        
        self.shell.poutput("\n--- Available Plugins ---")
        try:
            available = [name for _, name, _ in pkgutil.iter_modules(['plugins'])]
            if not available:
                self.shell.poutput("  No plugins found in the 'plugins' directory.")
            else:
                for name in sorted(available):
                    status = " (loaded)" if name in self.loaded_plugins else ""
                    self.shell.poutput(f"  - {name}{status}")
        except (ImportError, ModuleNotFoundError):
            self.shell.poutput("  Error: 'plugins' directory not found or is not a valid package.")
    
    @staticmethod
    def _find_plugin_class(module) -> Optional[Type[BasePlugin]]:
        """Find a BasePlugin subclass in a module."""
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                return obj
        return None
    
    @staticmethod
    def _has_default_handler(plugin_instance: BasePlugin) -> bool:
        """Check if a plugin overrides the default handler."""
        plugin_default = getattr(plugin_instance, 'default', None)
        base_default = getattr(BasePlugin, 'default', None)
        return plugin_default is not None and plugin_default != base_default
    
    
    def _register_commands(self, plugin_instance: BasePlugin) -> None:
        """Register a plugin's CommandSet with the shell, if applicable."""
        if isinstance(plugin_instance, cmd2.CommandSet):
            # This is the magic step that makes cmd2 aware of the new commands
            self.shell.register_command_set(plugin_instance)
            self.shell.poutput(f"Successfully registered command set from '{plugin_instance.name}'.")
    

    def _unregister_commands(self, plugin_instance: BasePlugin) -> None:
        """Unregister a plugin's CommandSet from the shell."""
        if isinstance(plugin_instance, cmd2.CommandSet):
            # This is the crucial cleanup step
            self.shell.unregister_command_set(plugin_instance)
            self.shell.poutput(f"Successfully unregistered command set from '{plugin_instance.name}'.")
    
    @staticmethod
    def _parse_plugin_args(arg_list: List[str]) -> Dict[str, Union[str, bool]]:
        """Parse command-line arguments into a kwargs dict."""
        kwargs: Dict[str, Union[str, bool]] = {}
        i = 0
        while i < len(arg_list):
            if arg_list[i].startswith('--'):
                key = arg_list[i][2:]
                if (i + 1) < len(arg_list) and not arg_list[i + 1].startswith('--'):
                    kwargs[key] = arg_list[i + 1]
                    i += 2
                else:
                    kwargs[key] = True
                    i += 1
            else:
                i += 1
        return kwargs
    
    @staticmethod
    def _print_error(message: str, exception: Exception) -> None:
        """Print formatted error information."""
        print("\n" + "=" * 70)
        print(f"--- {message} ---")
        print(f"Exception Type: {type(exception).__name__}")
        print(f"Exception Message: {exception}")
        print("\nFull Traceback:")
        print(traceback.format_exc())
        print("=" * 70 + "\n")
