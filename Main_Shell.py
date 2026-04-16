#!/usr/bin/env python


import argparse
import asyncio
import boto3
import aioboto3
from botocore.exceptions import ClientError
import json
import logging
import time
import importlib
import inspect
import pkgutil
import sys
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Set

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

# --- Import all AWS logic from your library ---
# This assumes you have a file named 'aws_lib.py' in the same directory
# or in Python's path.
from lib import aws_instances, aws_commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CommandHandler:
    def execute_distributable_command(self, command_string: str, target_instances: Dict[str, str]):
        raise NotImplementedError("This method must be implemented by a subclass.")

class SimpleCommandHandler(CommandHandler):
    def __init__(self, ssm_client=None):
        self.ssm_client = ssm_client if ssm_client is not None else boto3.client('ssm')

    def _send_command(self, command: str, instance_ids: List[str]) -> Optional[str]:
        document_name = 'AWS-RunShellScript'
        try:
            response = self.ssm_client.send_command(
                InstanceIds=instance_ids,
                DocumentName=document_name,
                Parameters={'commands': [command]},
                Comment=f'Interactive shell command: {command}'
            )
            command_id = response['Command']['CommandId']
            print(f"Command '{command}' sent with Command ID: {command_id}")
            return command_id
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidInstanceInformation':
                logging.error("An invalid instance ID was provided or an instance is not managed by SSM.")
            else:
                logging.error(f"An AWS API error occurred sending command: {e.response['Error']['Message']}")
            print("Error: Could not send command. Check logs for details.")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred sending command: {e}")
            print("Error: An unexpected error occurred. Check logs for details.")
            return None

    def _get_command_output(self, command_id: str, target_instances: Dict[str, str]):
        instance_ids = list(target_instances.keys())
        waiter = self.ssm_client.get_waiter('command_executed')

        for instance_id in instance_ids:
            instance_name = target_instances.get(instance_id, 'Unknown')
            print(f"\n--- Output for '{instance_name}' ({instance_id}) ---")
            try:
                waiter.wait(
                    CommandId=command_id,
                    InstanceId=instance_id,
                    WaiterConfig={'Delay': 2, 'MaxAttempts': 30}
                )
                result = self.ssm_client.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id,
                )
                if result['Status'] == 'Success':
                    print(result['StandardOutputContent'])
                else:
                    print(f"Command failed on this instance. Status: {result['Status']}")
                    print(f"Error Output:\n{result['StandardErrorContent']}")
            except Exception as e:
                logging.error(f"An error occurred getting output for {instance_id}: {e}")
                print(f"An error occurred while getting output for this instance. Check logs.")
            print(f"--- End of Output for '{instance_name}' ({instance_id}) ---")

    def execute_distributable_command(self, command_string: str, target_instances: Dict[str, str]):
        if not command_string or not target_instances:
            if not target_instances:
                print("No instances in the target group to execute the command on.")
            return
        
        instance_ids = list(target_instances.keys())
        command_id = self._send_command(command_string, instance_ids)
        if command_id:
            self._get_command_output(command_id, target_instances)
        else:
            logging.error(f"Execution failed: no command_id returned for command '{command_string}'.")

class AsyncCommandHandler(CommandHandler):
    def __init__(self, aio_session=None):
        self.session = aio_session if aio_session is not None else aioboto3.Session()

    async def _send_command(self, command: str, instance_ids: List[str]) -> Optional[str]:
        document_name = 'AWS-RunShellScript'
        async with self.session.client('ssm') as ssm_client:
            try:
                response = await ssm_client.send_command(
                    InstanceIds=instance_ids,
                    DocumentName=document_name,
                    Parameters={'commands': [command]},
                    Comment=f'Interactive shell command: {command}'
                )
                command_id = response['Command']['CommandId']
                print(f"Command '{command}' sent with Command ID: {command_id}. Waiting for output...")
                return command_id
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidInstanceInformation':
                    logging.error("An invalid instance ID was provided or an instance is not managed by SSM.")
                else:
                    logging.error(f"An AWS API error occurred sending command: {e.response['Error']['Message']}")
                print("Error: Could not send command. Check logs for details.")
                return None
            except Exception as e:
                logging.error(f"An unexpected error occurred sending command: {e}")
                print("Error: An unexpected error occurred. Check logs for details.")
                return None

    async def _get_single_instance_output(self, command_id: str, instance_id: str) -> Dict[str, Any]:
        async with self.session.client('ssm') as ssm_client:
            waiter = ssm_client.get_waiter('command_executed')
            try:
                await waiter.wait(
                    CommandId=command_id,
                    InstanceId=instance_id,
                    WaiterConfig={'Delay': 2, 'MaxAttempts': 30}
                )
                result = await ssm_client.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id,
                )
                return { 'InstanceId': instance_id, 'Status': result.get('Status', 'Error'), 'Output': result.get('StandardOutputContent', ''), 'Error': result.get('StandardErrorContent', '') }
            except Exception as e:
                logging.error(f"Exception while waiting for output from {instance_id}: {e}")
                return { 'InstanceId': instance_id, 'Status': 'FailedToFetch', 'Error': f"An exception occurred: {e}" }

    def _display_aggregated_output(self, results: List[Dict[str, Any]], target_instances: Dict[str, str]):
        print("\n--- Aggregated Command Output ---")
        results.sort(key=lambda r: target_instances.get(r['InstanceId'], ''))
        
        for result in results:
            instance_name = target_instances.get(result['InstanceId'], 'Unknown')
            print(f"\n--- Output for '{instance_name}' ({result['InstanceId']}) ---")
            print(f"Status: {result['Status']}")
            if result.get('Output'):
                print("--- Standard Output ---\n" + result['Output'].strip())
            if result.get('Error'):
                print("--- Standard Error ---\n" + result['Error'].strip())
            print(f"--- End of Output for '{instance_name}' ({result['InstanceId']}) ---")

    async def _get_command_output_async(self, command_id: str, target_instances: Dict[str, str]):
        tasks = [self._get_single_instance_output(command_id, iid) for iid in target_instances.keys()]
        aggregated_results = await asyncio.gather(*tasks)
        self._display_aggregated_output(aggregated_results, target_instances)
    
    async def execute_distributable_command(self, command_string: str, target_instances: Dict[str, str]):
        if not command_string or not target_instances:
            if not target_instances:
                print("No instances in the target group to execute the command on.")
            return

        instance_ids = list(target_instances.keys())
        command_id = await self._send_command(command_string, instance_ids)
        if command_id:
            await self._get_command_output_async(command_id, target_instances)
        else:
            logging.error(f"Execution failed: Could not send command '{command_string}'.")

class AwsInstance:
    def __init__(self, identifier: str, ec2_client=None, ssm_client=None):
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        self.ssm_client = ssm_client if ssm_client is not None else boto3.client('ssm')
        self.identifier = identifier
        self.description = None
        self._is_valid = self._resolve()

    def _resolve(self) -> bool:
        if not self.identifier:
            return False
            
        try:
            if self.identifier.startswith('i-'):
                response = self.ec2_client.describe_instances(InstanceIds=[self.identifier])
            else:
                response = self.ec2_client.describe_instances(
                    Filters=[
                        {'Name': 'tag:Name', 'Values': [self.identifier]},
                        {'Name': 'instance-state-name', 'Values': ['running']}
                    ]
                )
            
            instances = [inst for r in response.get('Reservations', []) for inst in r.get('Instances', [])]
            
            if len(instances) != 1:
                logging.warning(f"Failed to resolve '{self.identifier}' to a single instance. Found: {len(instances)}.")
                return False
            
            self.description = instances[0]
            return True 
        except ClientError as e:
            logging.error(f"AWS API error resolving '{self.identifier}': {e}")
            return False

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def is_ready(self) -> bool:
        """
        Checks if an instance is in a valid state to receive SSM commands.
        Returns True if the instance is running AND the SSM agent is online.
        """
        instance_id = self.get_id()
        # 1. First, check if we have a valid, running EC2 instance.
        if not self.is_valid or self.description.get('State', {}).get('Name') != 'running':
            return False

        # 2. If it's running, check the SSM agent's status.
        try:
            info = self.ssm_client.describe_instance_information(
                InstanceInformationFilterList=[{'key': 'InstanceIds', 'valueSet': [instance_id]}]
            )
            
            # If the list is empty, SSM doesn't know about this instance.
            if not info.get('InstanceInformationList'):
                return False
            
            # Check if the first result shows the agent is online.
            return info['InstanceInformationList'][0].get('PingStatus') == 'Online'

        except ClientError as e:
            logging.error(f"AWS API error checking SSM status for '{self.id}': {e}")
            return False

    def get_id(self) -> Optional[str]:
        if not self._is_valid or not self.description:
            return None
            
        return self.description.get('InstanceId')

    def get_name(self) -> Optional[str]:
        if not self._is_valid or not self.description:
            return None
        
        instance_name = self.get_id() # Default to ID
        for tag in self.description.get('Tags', []):
            if tag.get('Key') == 'Name' and tag.get('Value'):
                instance_name = tag.get('Value')
                break
        return instance_name
        
class StrippedAwsInstance:
    def __init__(self, possible_identifier: str, ec2_client=None):
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        heavy_instance = AwsInstance(identifier=possible_identifier, ec2_client=self.ec2_client)
        
        self.id = None
        self.name = None
        self.is_valid = False

        if heavy_instance.is_valid and heavy_instance.is_ready:
            self.id = heavy_instance.get_id()
            self.name = heavy_instance.get_name()
            self.is_valid = heavy_instance.is_valid

    
    # --- Essential methods for list/set operations ---
    def __eq__(self, other):
        if not isinstance(other, StrippedAwsInstance):
            return NotImplemented
        
        # If both instances are valid, compare their IDs.
        if self.is_valid and other.is_valid:
            return self.id == other.id
        
        # If both instances are invalid, they are considered equal.
        if not self.is_valid and not other.is_valid:
            return True
            
        # If one is valid and the other is not, they are not equal.
        return False

    def __hash__(self):
        if self.is_valid:
            return hash(self.id)
        else:
            return hash(self.identifier)

    def __repr__(self):
        if self.is_valid:
            return f"StrippedAwsInstance(id='{self.id}', name='{self.name}')"
        else:
            return f"StrippedAwsInstance(invalid_identifier='{self.identifier}')"
            
class InstanceGroup:
    def __init__(self, ec2_client=None, initial_instances: Optional[List[str]] = None): 
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        self._instances: Set[StrippedAwsInstance] = set()
        logging.debug("Created new InstanceGroup object")
        if initial_instances:
            self.add_instances(initial_instances)

    def add_instances(self, instance_list: List[str]):
        if not instance_list:
            logging.warning("No instances specified to add")
            return

        existing_identifiers = {inst.id for inst in self._instances} | {inst.name for inst in self._instances}

        for item in instance_list:
            if item in existing_identifiers:
                print(f"Instance '{item}' is already in the group.")
                continue # Skip to the next item in the list

            # If not already present, try to resolve the new instance.
            instance = StrippedAwsInstance(possible_identifier=item, ec2_client=self.ec2_client)
            
            if instance.is_valid:
                # A resolved instance could still be a duplicate if added via a different alias
                # (e.g., adding by ID when it was already added by name). The set handles this.
                if instance not in self._instances:
                    logging.debug(f"{type(self._instances)}")
                    self._instances.add(instance)
                    # Add the new instance's ID and name to our lookup set for this session
                    existing_identifiers.add(instance.id)
                    existing_identifiers.add(instance.name)
                    print(f"Added instance '{instance.name}' ({instance.id}) to group.")
                else:
                    print(f"Instance '{item}' is already in the group (added via a different name/ID).")
            else:
                print(f"Warning: Could not resolve '{item}' to a valid instance.")

    def remove_instances(self, removal_list: List[str]):
        if not removal_list: return
        removal_set = set(removal_list)
        
        # Use the renamed attribute
        instances_to_remove = {inst for inst in self._instances if inst.name in removal_set or inst.id in removal_set}
        
        if not instances_to_remove:
            print("No matching instances found in the group to remove.")
            return

        # Use the renamed attribute
        self._instances -= instances_to_remove
        print(f"Removed {len(instances_to_remove)} instance(s).")
                

    def get_instances(self) -> Dict[str, str]:
        return {inst.id: inst.name for inst in self._instances if inst.id}

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

class AWSInteractiveShellCompleter(Completer):
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


class AWSInteractiveShell:
    """
    The main application class, responsible for the shell UI, command parsing,
    and plugin management. It contains no direct AWS logic.
    """
    def __init__(self, instance_list: Optional[List[str]] = None, use_async: bool = False):
        self.use_async = use_async
        self.history_filename = 'AWSInteractiveShell_history.txt'

        self.ec2_client = boto3.client('ec2')
                        
        # Instantiate objects from the AWS library
        self.instance_group = aws_instances.InstanceGroup(ec2_client=self.ec2_client, initial_instances=instance_list)
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

    def _handle_input(self, input_string: str):
        """
        Parses user input. If the first word is a known command, it's handled
        internally. Otherwise, the entire string is treated as a remote command.
        """
        parts = input_string.strip().split()
        if not parts:
            return

        command = parts[0]

        # STAGE 1: Check if the first word is a known internal command.
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
            print(f"'{command}' is not a recognized internal command. Attempting to execute on remote instances...")
            self._handle_command(input_string)
            return

    def _handle_command(self, command_string):
        targets = self.instance_group.get_instances()
        if self.use_async:
            asyncio.run(self.command_handler.execute_distributable_command(command_string, targets))
        else:
            self.command_handler.execute_distributable_command(command_string, targets)

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
    parser = argparse.ArgumentParser(
        description="An interactive web shell for managing and executing commands on EC2 instances."
    )
    parser.add_argument('--mode', type=str, choices=['async', 'sync'], default='async', help="The execution mode.")
    parser.add_argument('--instances', nargs='*', help="Initial instance IDs or names.")
    args = parser.parse_args()
    
    shell = AWSInteractiveShell(instance_list=args.instances, use_async=(args.mode == 'sync'))
    shell.start()

if __name__ == "__main__":
    cli()
