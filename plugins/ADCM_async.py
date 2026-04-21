import argparse
import asyncio
import cmd2
import boto3
import aioboto3
from typing import List, Optional

from plugin_interface import BasePlugin
from lib.aws_instances import InstanceGroup
from lib.aws_commands import AsyncCommandHandler

class AWSPlugin(BasePlugin, cmd2.CommandSet):
    """
    This is a 'mixin' class for cmd2. It provides all AWS-related commands
    and functionality to the main shell.
    """
    def __init__(self, initial_instances: Optional[List[str]] = None):
        self._instance_group = InstanceGroup(initial_instances=initial_instances)
        self._command_handler = AsyncCommandHandler()
        self._shell: Optional[cmd2.Cmd] = None
        print("AWS Distributed Command Manager (ASYNC) Plugin Loaded.")

    @property
    def name(self) -> str:
        """The unique name of the plugin."""
        return "ADCM_async"

    def set_shell(self, shell: cmd2.Cmd) -> None:
        """Set the reference to the cmd2 shell instance."""
        self._shell = shell

    # --- Default Command Handler for Remote Execution ---
    def default(self, statement: str):
        """
        This method is called by cmd2 for any command that is not a
        built-in shell command.
        """
        self._shell.poutput(f"'{statement.split()[0]}' is not a built-in command. Passing to AWS Distributed command handler...")
        targets = self._instance_group.get_instances()
        asyncio.run(self._command_handler.execute_distributable_command(statement, targets))
        

    # --- 'group' Sub-commands ---
    
    # Create an argparser for commands that take a list of instances
    instance_parser = argparse.ArgumentParser()
    instance_parser.add_argument('instances', nargs='+', help='One or more instance names or IDs')
    
    @cmd2.with_argparser(instance_parser)
    def do_group_add(self, args: argparse.Namespace):
        """Add one or more instances to the current target group."""
        self._instance_group.add_instances(args.instances)

    @cmd2.with_argparser(instance_parser)
    def do_group_remove(self, args: argparse.Namespace):
        """Remove one or more instances from the current target group."""
        self._instance_group.remove_instances(args.instances)

    def do_group_show(self, args: str):
        """Show the instances currently in the target group."""
        targets = self._instance_group.get_instances()
        if not targets:
            self._shell.poutput("No instances are currently in the target group.")
        else:
            output = "Current target instances:\n"
            for inst in sorted(list(targets), key=lambda i: i.name):
                output += f"  - {inst.name} ({inst.id})\n"
            self._shell.poutput(output)

        
    # Create an argparser for commands that take a single filename
    file_parser = argparse.ArgumentParser()
    file_parser.add_argument('filename', help='The filename for the group file (e.g., my-group)')
    
    """
    @cmd2.with_argparser(file_parser)
    def do_group_save(self, args: argparse.Namespace):
        # Saves the current instance group to a JSON file.
        # ... (implementation is the same, just uses self._instance_group)
        pass

    @cmd2.with_argparser(file_parser)
    def do_group_load(self, args: argparse.Namespace):
        #Loads an instance group from a JSON file.
        # ... (implementation is the same, just uses self._instance_group)
        pass
        
    def do_group_check_health(self, args: str):
        #Checks the SSM readiness of all instances in the group.
        # ... (implementation is the same, just uses self._instance_group)
        pass
    """