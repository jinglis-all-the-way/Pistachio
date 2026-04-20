import argparse
import cmd2
from typing import List, Optional

#from plugin_interface import BasePlugin
from lib.aws_instances import InstanceGroup
from lib.aws_commands import SimpleCommandHandler


class AWSPlugin(cmd2.CommandSet):
    """
    This is a 'mixin' class for cmd2. It provides all AWS-related commands
    and functionality to the main shell.
    """
    def __init__(self, initial_instances: Optional[List[str]] = None):
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
        if self._shell:
            self._shell.poutput(f"'{statement.raw}' is not a built-in command. Passing to AWS command handler...")
        targets = self._instance_group.get_instances()
        
        self._command_handler.execute_distributable_command(statement, targets)

    # --- 'group' Sub-commands ---
    
    # Create an argparser for commands that take a list of instances
    instance_parser = argparse.ArgumentParser()
    instance_parser.add_argument('instances', nargs='+', help='One or more instance names or IDs')
    
    # --- Command Methods ---
    # These 'do_*' methods will be copied onto the main shell instance.

    def do_group(self, arg_string: str):
        """Category command for AWS group management."""
        self._shell.poutput("Group management commands: add, remove, show, save, load")

    def do_group_add(self, arg_string: str):
        """Add one or more instances to the current target group."""
        if not arg_string:
            self._shell.poutput("Usage: group add <instance_id_or_name> ...")
            return
        
        instance_list = arg_string.split()
        self._instance_group.add_instances(instance_list)

    def do_group_remove(self, arg_string: str):
        """Remove one or more instances from the current target group."""
        if not arg_string:
            self._shell.poutput("Usage: group remove <instance_id_or_name> ...")
            return

        self._instance_group.remove_instances(arg_string.split())

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
            
   # # Create an argparser for commands that take a single filename
    #file_parser = argparse.ArgumentParser()
    #file_parser.add_argument('filename', help='The filename for the group file (e.g., my-group)')
    
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
