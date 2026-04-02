# shell.py

import argparse
import asyncio
import json
import logging
import importlib
import inspect
import pkgutil
import sys
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

# --- Import all AWS logic from your library ---
# This assumes you have a file named 'aws_lib.py' in the same directory
# or in Python's path.
from lib import aws_instances, aws_commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BasePlugin(ABC):
    """Abstract base class defining the contract for all plugins."""
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def commands(self) -> dict:
        pass

class AWSShellCompleter(Completer):
    """Handles contextual command auto-completion."""
    def __init__(self, command_tree: Dict[str, Any]):
        self.command_tree = command_tree

    def get_completions(self, document: Document, complete_event) -> None:
        text = document.text_before_cursor
        words = text.lstrip().split()

        if text and text[-1].isspace():
            words.append('')

        current_node = self.command_tree
        
        for i, word in enumerate(words[:-1]):
            if isinstance(current_node, dict) and word in current_node:
                current_node = current_node[word]
            else:
                current_node = None
                break
        
        if isinstance(current_node, dict):
            word_to_complete = words[-1]
            for key in sorted(current_node.keys()):
                if key.startswith('_'):
                    continue
                if key.startswith(word_to_complete):
                    yield Completion(
                        key,
                        start_position=-len(word_to_complete),
                        display_meta=current_node[key].get('_description', '') if isinstance(current_node.get(key), dict) else ''
                    )


class AWSShell:
    """
    The main application class, responsible for the shell UI, command parsing,
    and plugin management. It contains no direct AWS logic.
    """
    def __init__(self, instance_list: Optional[List[str]] = None, use_async: bool = False):
        self.use_async = use_async
        
        # Instantiate objects from the AWS library
        self.instance_group = aws_instances.InstanceGroup(initial_instances=instance_list)
        self.command_handler = aws_commands.AsyncCommandHandler() if use_async else aws_commands.SimpleCommandHandler()
        
        self.loaded_plugins = {}
        
        # Define the command structure for the shell
        self.commands = {
            'list': lambda *args: self._list_sub_commands(self.commands, *args),
            'exit': self._exit_shell, 'quit': self._exit_shell,
            'plugin': {
                '_description': 'Manage shell plugins.',
                'list': self._list_plugins,
                'load': self._load_plugin,
                'unload': self._unload_plugin,
            },
            'shell': {
                '_description': 'Commands related to the shell session itself.',
                'list': lambda *args: self._list_sub_commands(self.commands['shell'], *args),
                'history': {
                    '_description': 'View and rerun command history.',
                    'show': self._show_history,
                    'clear': self._clear_history,
                },
                'group': {
                    '_description': 'Commands for managing the instance group.',
                    'list': lambda *args: self._list_sub_commands(self.commands['shell']['group'], *args),
                    'add': self.instance_group.add_instances,
                    'remove': self.instance_group.remove_instances,
                    'show': self._show_targets,
                    'save': self._save_group,
                    'load': self._load_group,
                }
            }
        }
        
        completer = AWSShellCompleter(self.commands)
        self.prompt_session = PromptSession(
            history=FileHistory('shell_history.txt'),
            completer=completer,
            complete_while_typing=True
        )
        self.history = list(self.prompt_session.history.get_strings())

    def _list_sub_commands(self, command_node, *args):
        print("Available commands:")
        for key, value in command_node.items():
            if not key.startswith('_'):
                description = value.get('_description', '') if isinstance(value, dict) else ''
                print(f"  - {key:<15} {description}")

    def _show_history(self, *args):
        self.history = list(self.prompt_session.history.get_strings())
        if not self.history:
            print("No commands in history yet.")
            return
        print("\n--- Command History ---")
        for i, cmd in enumerate(self.history, 1):
            print(f"{i: >3}: {cmd}")

    def _clear_history(self, *args):
        # It's good practice to ask for confirmation for destructive actions
        confirm = input("Are you sure you want to permanently clear all command history? [y/N]: ")
        if confirm.lower() != 'y':
            print("History clear aborted.")
            return

        try:
            history = self.prompt_session.history
            
            # Clear the in-memory history list
            history.clear()
            
            # Truncate the history file on disk by opening it in write mode
            with open(history.filename, 'w') as f:
                pass  # Opening in 'w' mode and closing is enough to clear it
            
            self.history.clear()
            
            print("Command history has been cleared.")
        
        except Exception as e:
            print(f"An error occurred while clearing history: {e}")

    def _show_targets(self, *args):
        targets = self.instance_group.get_instances()
        if not targets:
            print("No instances are currently in the target group.")
        else:
            print("Current target instances:")
            for instance_id, instance_name in targets.items():
                print(f"  - {instance_name} ({instance_id})")

    def _exit_shell(self, *args):
        print("Exiting shell.")
        return 'exit'

    def _save_group(self, *args):
        if not args:
            print("Error: Please provide a filename. Usage: shell group save <filename>")
            return
        filename = args[0] if args[0].endswith('.json') else f"{args[0]}.json"
        try:
            # get_instances returns a dict, which is perfect for JSON
            with open(filename, 'w') as f:
                json.dump(self.instance_group.get_instances(), f, indent=4)
            print(f"Instance group saved to '{filename}'.")
        except Exception as e:
            print(f"Error saving group to '{filename}': {e}")

    def _load_group(self, *args):
        if not args:
            print("Error: Please provide a filename. Usage: shell group load <filename>")
            return
        filename = args[0] if args[0].endswith('.json') else f"{args[0]}.json"
        try:
            with open(filename, 'r') as f:
                loaded_instances_dict = json.load(f)
            
            # Re-add the instances from the file
            self.instance_group.instances.clear() # Clear the current group
            self.instance_group.add_instances(list(loaded_instances_dict.keys()))
            print(f"Instance group loaded from '{filename}'.")
            self._show_targets()
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            print(f"Error loading group from '{filename}': {e}")
            
    def _describe_instance(self, *args):
        if not args:
            print("Error: Please provide an instance name.")
            return
        description = self.instance_group.get_instance_description_by_name(args[0])
        if description:
            print(json.dumps(description, indent=4, default=str))

    def _list_plugins(self, *args):
        print("--- Loaded Plugins ---")
        if not self.loaded_plugins:
            print("  No plugins are currently loaded.")
        else:
            for name in self.loaded_plugins.keys():
                print(f"  - {name}")

        print("\n--- Available Plugins (in 'plugins/' directory) ---")
        try:
            available = [name for _, name, _ in pkgutil.iter_modules(['plugins'])]
            if not available:
                print("  No plugins found in the 'plugins' directory.")
            else:
                for name in available:
                    status = "(loaded)" if name in self.loaded_plugins else ""
                    print(f"  - {name} {status}")
        except FileNotFoundError:
            print("  'plugins' directory not found.")

    def _load_plugin(self, *args):
        if not args:
            print("Error: Please provide a plugin name to load.")
            return
        plugin_name = args[0]
        if plugin_name in self.loaded_plugins:
            print(f"Error: Plugin '{plugin_name}' is already loaded.")
            return
        try:
            module = importlib.import_module(f"plugins.{plugin_name}")
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin_instance = obj()
                    for command_name in plugin_instance.commands.keys():
                        if command_name in self.commands:
                            print(f"Error: Command '{command_name}' from plugin '{plugin_name}' conflicts. Not loading.")
                            return
                    self.commands.update(plugin_instance.commands)
                    self.loaded_plugins[plugin_name] = plugin_instance
                    print(f"Plugin '{plugin_name}' loaded successfully.")
                    return
            print(f"Error: No valid plugin class found in '{plugin_name}.py'.")
        except ImportError:
            print(f"Error: Plugin '{plugin_name}' not found.")
        except Exception as e:
            print(f"An unexpected error occurred while loading plugin '{plugin_name}': {e}")

    def _unload_plugin(self, *args):
        if not args:
            print("Error: Please provide a plugin name to unload.")
            return
        plugin_name = args[0]
        if plugin_name not in self.loaded_plugins:
            print(f"Error: Plugin '{plugin_name}' is not currently loaded.")
            return
        try:
            plugin_instance = self.loaded_plugins[plugin_name]
            for command_name in plugin_instance.commands.keys():
                if command_name in self.commands:
                    del self.commands[command_name]
            del self.loaded_plugins[plugin_name]
            if f"plugins.{plugin_name}" in sys.modules:
                del sys.modules[f"plugins.{plugin_name}"]
            print(f"Plugin '{plugin_name}' unloaded successfully.")
        except Exception as e:
            print(f"An unexpected error occurred while unloading plugin '{plugin_name}': {e}")

    def _handle_command(self, command_string: str):
        parts = command_string.strip().split()
        if not parts: return

        current_node = self.commands
        for i, part in enumerate(parts):
            if isinstance(current_node, dict) and part in current_node:
                current_node = current_node[part]
                if i == len(parts) - 1:
                    if callable(current_node):
                        return current_node(*parts[i+1:])
                    elif isinstance(current_node, dict):
                        print(f"Sub-commands for '{' '.join(parts)}':")
                        self._list_sub_commands(current_node)
                        return
            else:
                print(f"'{part}' is not a recognized internal command. Attempting to execute on remote instances...")
                targets = self.instance_group.get_instances()
                if self.use_async:
                    asyncio.run(self.command_handler.execute_distributable_command(command_string, targets))
                else:
                    self.command_handler.execute_distributable_command(command_string, targets)
                return
        
        print(f"Invalid command: '{command_string}'")

    def start(self):
        mode = "Asynchronous" if self.use_async else "Simplex"
        print(f"\nShell started in {mode} mode. Press Tab for auto-completion. Enter 'list' to see commands.")
        
        while True:
            try:
                cmd_input = self.prompt_session.prompt("\n>> ")
                if not cmd_input.strip(): continue
                if self._handle_command(cmd_input) == 'exit':
                    break
            except (KeyboardInterrupt, EOFError):
                print("\nExiting shell.")
                break

def cli():
    parser = argparse.ArgumentParser(
        description="An interactive web shell for managing and executing commands on EC2 instances."
    )
    parser.add_argument('--mode', type=str, choices=['async', 'sync'], default='async', help="The execution mode.")
    parser.add_argument('--instances', nargs='*', help="Initial instance IDs or names.")
    args = parser.parse_args()
    
    shell = AWSShell(instance_list=args.instances, use_async=(args.mode == 'sync'))
    shell.start()

if __name__ == "__main__":
    cli()
