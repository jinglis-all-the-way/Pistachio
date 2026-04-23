import argparse
import cmd2
from typing import List, Optional

from plugin_interface import BasePlugin
from lib.aws_instances import InstanceGroup
from lib.aws_commands import SimpleCommandHandler


class AWSPlugin(BasePlugin, cmd2.CommandSet):
    """AWS plugin for TacoShell providing instance and command management."""
    
    def __init__(self, initial_instances: Optional[List[str]] = None):
        super().__init__()
        self._instance_group = InstanceGroup(initial_instances=initial_instances)
        self._command_handler = SimpleCommandHandler()
        self._shell: Optional[cmd2.Cmd] = None
        print("AWS Distributed Command Manager Plugin Loaded.")

    @property
    def name(self) -> str:
        """The unique name of the plugin."""
        return "ADCM"

    def set_shell(self, shell: cmd2.Cmd) -> None:
        """Set the reference to the cmd2 shell instance."""
        self._shell = shell

    # --- Default Command Handler for Remote Execution ---
    def default(self, statement: str):
        """
        This method is called by cmd2 for any command that is not a
        built-in shell command.
        """
        commands_to_run = statement.raw
        if self._shell:
            self._shell.poutput(f"'{commands_to_run}' is not a built-in command. Passing to AWS command handler...")
        targets = self._instance_group.get_instances()
        
        self._command_handler.execute_distributable_command(commands_to_run, targets)

    # --- 'group' Sub-commands ---
    
    # Create an argparser for commands that take a list of instances

    group_parser = cmd2.Cmd2ArgumentParser(description='Manage plugins')
    group_subparsers = group_parser.add_subparsers(title='subcommands', help='group subcommands')
    
    # group add subcommand
    gadd_parser = group_subparsers.add_parser('add', help='One or more AWS instances by name or ID')
    
    # group remove subcommand
    gremove_parser = group_subparsers.add_parser('remove', help='One or more AWS instances by name or ID')
    
    # group show subcommand
    gshow_parser = group_subparsers.add_parser('list', help='Show the current group')

    # --- Command Methods ---
    # These 'do_*' methods will be copied onto the main shell instance.
    @cmd2.with_argparser(group_parser)
    def do_group(self, arg_string: str):
        """Category command for AWS group management."""
        self._shell.poutput("Group management commands: add, remove, show")

    @cmd2.with_argparser(gadd_parser)
    def do_group_add(self, arg_string: str):
        """Add one or more instances to the current target group."""
        if not arg_string:
            self._shell.poutput("Usage: group add <instance_id_or_name> ...")
            return
        
        instance_list = arg_string.split()
        self._instance_group.add_instances(instance_list)

    @cmd2.with_argparser(gremove_parser)
    def do_group_remove(self, arg_string: str):
        """Remove one or more instances from the current target group."""
        if not arg_string:
            self._shell.poutput("Usage: group remove <instance_id_or_name> ...")
            return

        self._instance_group.remove_instances(arg_string.split())

    @cmd2.with_argparser(gshow_parser)
    def do_group_show(self, arg_string: str):
        """Show the instances currently in the target group."""
        targets = self._instance_group.get_instance_objects()
        if not targets:
            self._shell.poutput("No instances are currently in the target group.")
        else:
            output = "Current target instances:\n"
            for inst in sorted(list(targets), key=lambda i: i.name):
                output += f"  - {inst.name} ({inst.id})\n"
            self._shell.poutput(output)
            
  