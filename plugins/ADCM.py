import argparse
import cmd2
from typing import List, Optional

from plugin_interface import BasePlugin
from lib.aws_instances import InstanceGroup
from lib.aws_commands import SimpleCommandHandler


class AWSPlugin(BasePlugin, cmd2.CommandSet):
    """AWS plugin for TacoShell providing instance and command management."""
    
    def __init__(self, initial_instances: Optional[List[str]] = None):
        BasePlugin.__init__(self)
        cmd2.CommandSet.__init__(self)
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

    group_parser = cmd2.Cmd2ArgumentParser(description='Group management commands: add, remove, show')
    group_subparsers = group_parser.add_subparsers(title='subcommands', help='group subcommands')
    
    # group add subcommand
    group_add_parser = group_subparsers.add_parser('add', help='Adds indicated instances to the target group')
    group_add_parser.add_argument('instances', help='One or more AWS instances by name or ID')
    
    # group remove subcommand
    group_remove_parser = group_subparsers.add_parser('remove', help='Removes indicated instances from the target group')
    group_remove_parser.add_argument('instances', help='One or more AWS instances by name or ID')

    # group show subcommand
    group_show_parser = group_subparsers.add_parser('list', help='Show the current group')

    # --- Command Methods ---
    # These 'do_*' methods will be copied onto the main shell instance.
    @cmd2.with_argparser(group_parser)
    def do_group(self, args: argparse.Namespace) -> None:
        """Category command for AWS group management."""
        if not hasattr(args, 'func'):
            self._shell.poutput(args.format_help())
            return
        
        handler_name = args.func
        if handler_name == '_handle_group_add':
            self._handle_group_add(args)
        elif handler_name == '_handle_group_remove':
            self._handle_group_remove(args)
        elif handler_name == '_handle_group_show':
            self._handle_group_show(args)

    def _handle_group_add(self, args: argparse.Namespace):
        """Add one or more instances to the current target group."""
        instances_to_add = args.instances if hasattr(args, 'instances') else []
        
        instance_list = instances_to_add.split()
        self._instance_group.add_instances(instance_list)

    def _handle_group_remove(self, args: argparse.Namespace):
        """Remove one or more instances from the current target group."""
        if not arg_string:
            self._shell.poutput("Usage: group remove <instance_id_or_name> ...")
            return

        self._instance_group.remove_instances(arg_string.split())

    def _handle_group_show(self, args: argparse.Namespace):
        """Show the instances currently in the target group."""
        targets = self._instance_group.get_instance_objects()
        if not targets:
            self._shell.poutput("No instances are currently in the target group.")
        else:
            output = "Current target instances:\n"
            for inst in sorted(list(targets), key=lambda i: i.name):
                output += f"  - {inst.name} ({inst.id})\n"
            self._shell.poutput(output)
            
  