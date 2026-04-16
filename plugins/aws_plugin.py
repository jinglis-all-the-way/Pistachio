# aws_plugin.py

import argparse
import asyncio
import boto3
import aioboto3
from typing import List

# Import all your existing, correct AWS data classes
# NOTE: These classes (AwsInstance, etc.) do not need to be changed.
from aws_lib import InstanceGroup, SimpleCommandHandler, AsyncCommandHandler

class AWSPlugin:
    """
    This is a 'mixin' class for cmd2. It provides all AWS-related commands
    and functionality to the main shell.
    """
    def __init__(self, use_async=True, initial_instances=None):
        self._use_async = use_async
        self._instance_group = InstanceGroup(initial_instances=initial_instances)
        self._command_handler = AsyncCommandHandler() if use_async else SimpleCommandHandler()
        print("AWS Plugin Loaded.")

    # --- Default Command Handler for Remote Execution ---
    def default(self, statement: str):
        """
        This method is called by cmd2 for any command that is not a
        built-in shell command.
        """
        self._shell.poutput(f"'{statement.split()[0]}' is not a built-in command. Passing to AWS command handler...")
        targets = self._instance_group.get_instances()
        if self._use_async:
            asyncio.run(self._command_handler.execute_distributable_command(statement, targets))
        else:
            self._command_handler.execute_distributable_command(statement, targets)

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
        targets = self._instance_group.get_instance_objects()
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
    
    @cmd2.with_argparser(file_parser)
    def do_group_save(self, args: argparse.Namespace):
        """Saves the current instance group to a JSON file."""
        # ... (implementation is the same, just uses self._instance_group)
        pass

    @cmd2.with_argparser(file_parser)
    def do_group_load(self, args: argparse.Namespace):
        """Loads an instance group from a JSON file."""
        # ... (implementation is the same, just uses self._instance_group)
        pass
        
    def do_group_check_health(self, args: str):
        """Checks the SSM readiness of all instances in the group."""
        # ... (implementation is the same, just uses self._instance_group)
        pass
