# webshell.py

import argparse
import logging
import importlib, inspect, pkgutil, sys
from abc import ABC, abstractmethod
from typing import Dict, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BasePlugin(ABC):
    """The contract for all plugins."""
    @property
    @abstractmethod
    def name(self) -> str: pass

    @property
    @abstractmethod
    def commands(self) -> dict: pass

    def default_handler(self, command_string: str):
        """Optional: A fallback method for commands not handled by the shell."""
        print(f"Error: Command '{command_string.split()[0]}' not found.")

class TacoShellCompleter(Completer):
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

class TacoShell:
    """A generic, extensible shell framework."""
    def __init__(self):
        self.history_filename = 'tacoshell_history.txt'
        self.loaded_plugins = {}
        # The default handler is None until a plugin registers one.
        self.default_command_handler = None
        
        # The core command tree is now very minimal.
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
                    '_description': 'Show and clear command history.',
                    'show': self._show_history,
                    'clear': self._clear_history,
                },
            },
        }
        
        self.prompt_session = self._create_prompt_session()
        self.history = list(self.prompt_session.history.get_strings())

    def _create_prompt_session(self) -> PromptSession:
        """Creates and configures the PromptSession object."""
        completer = AWSInteractiveShellCompleter(self.commands)
        return PromptSession(
            history=FileHistory(self.history_filename),
            completer=completer,
            complete_while_typing=True
        )

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
            # Truncate the history file using the class attribute
            with open(self.history_filename, 'w') as f:
                pass
            
            # Re-create the session, which will implicitly use the same filename
            self.prompt_session = self._create_prompt_session()
            
            self.history.clear()
            
            print("Command history has been cleared.")

    def _exit_shell(self, *args):
        print("Exiting shell.")
        return 'exit'

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

        # --- MODIFICATION: After loading, check if the plugin provides a default handler ---
        if hasattr(plugin_instance, 'default_handler') and callable(plugin_instance.default_handler):
            if self.default_command_handler is not None:
                print(f"Warning: Plugin '{plugin_name}' is overriding the existing default command handler.")
            self.default_command_handler = plugin_instance.default_handler
            print(f"Plugin '{plugin_name}' has registered as the default command handler.")


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
        
        # --- MODIFICATION: If the unloaded plugin was the default handler, remove it ---
        if self.default_command_handler == plugin_instance.default_handler:
            self.default_command_handler = None
            print(f"Unregistered default command handler from plugin '{plugin_name}'.")

    def _handle_input(self, input_string: str):
        def _handle_input(self, input_string: str):
        """
        Parses user input. If the first word is a known command, it's handled
        internally. Otherwise, the entire string is treated as a remote command.
        """
        parts = input_string.strip().split()
        if not parts:
            return

        command = parts[0]

        if command in self.commands:
            # It's an internal command. Proceed to parse its arguments and sub-commands.
            current_node = self.commands[command]
            
            # Loop through the rest of the parts (the sub-commands and arguments)
            for i, part in enumerate(parts[1:], 1): # Start from the second word
                if isinstance(current_node, dict) and part in current_node:
                    current_node = current_node[part]
                else:
                    # This happens if a valid function is followed by extra arguments.
                    # e.g., "shell group add my-instance-name"
                    if callable(current_node):
                        return current_node(parts[i:])
                    else:
                        print(f"Invalid sub-command: '{part}' for command '{' '.join(parts[:i])}'")
                        return

            # After the loop, handle the final node
            if callable(current_node):
                return current_node() # Call function with no arguments
            elif isinstance(current_node, dict):
                print(f"Sub-commands for '{command}':")
                self._list_sub_commands(current_node)
                return

        # STAGE 2: If the first word was not in the command tree, treat it as a remote command.
        else:
            # If the command is not a built-in, delegate to the registered default handler.
            if self.default_command_handler:
                self.default_command_handler(input_string)
            else:
                print(f"Error: Command '{command}' not found. No default handler is loaded.")
            return

    def start(self):
        mode = "Asynchronous" if self.use_async else "Simplex"
        print(f"\nShell started in {mode} mode. Press Tab for auto-completion. Enter 'list' to see commands.")
        
        while True:
            try:
                cmd_input = self.prompt_session.prompt("\n>> ")
                if not cmd_input.strip(): continue
                if self._handle_input(cmd_input) == 'exit':
                    break
            except (KeyboardInterrupt, EOFError):
                print("\nExiting shell.")
                break

def cli():
    parser = argparse.ArgumentParser(description="An extensible, interactive shell.")
    args = parser.parse_args()
    
    shell = TacoShell()
    shell.start()

if __name__ == "__main__":
    cli()

