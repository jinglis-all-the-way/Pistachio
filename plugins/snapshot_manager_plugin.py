# plugins/snapshot_manager.py
import argparse
import cmd2
from typing import List, Optional

from plugin_interface import BasePlugin
from lib.aws_instances import InstanceGroup
from lib.aws_snapshots import *

class SnapshotManagerPlugin(BasePlugin, cmd2.CommandSet):
    """AWS plugin for TacoShell providing snapshot management."""
    def __init__(self, initial_instances: Optional[List[str]] = None):
        BasePlugin.__init__(self)
        cmd2.CommandSet.__init__(self)
        self._instance_group = InstanceGroup(initial_instances=initial_instances)
        
        self._shell: Optional[cmd2.Cmd] = None
        print("AWS Snapshot Manager Plugin Loaded.")

    @property
    def name(self) -> str:
        return "AWS Snapshot Manager"

    def set_shell(self, shell: cmd2.Cmd) -> None:
        """Set the reference to the cmd2 shell instance."""
        self._shell = shell

    # --- 'snapshot' Sub-commands ---  
    
    # Create an argparser for commands that take a list of instances

    snapshot_parser = cmd2.Cmd2ArgumentParser(description='snapshot management. Use this command to view, take and restore from snapshots, as well as remove old snapshots')
    snapshot_subparsers = snapshot_parser.add_subparsers(title='subcommands', dest='subcommand', help='snapshot subcommands')
    
    # snapshot add subcommand
    snapshot_create_parser = snapshot_subparsers.add_parser('add', help='Adds indicated instances to the target snapshot')
    snapshot_create_parser.add_argument('instances', nargs='+', help='One or more AWS instances by name or ID')
    snapshot_create_parser.set_defaults(func='_handle_snapshot_add')

    # snapshot remove subcommand
    snapshot_remove_parser = snapshot_subparsers.add_parser('remove', help='Removes indicated instances from the target snapshot')
    snapshot_remove_parser.add_argument('instances', nargs='+', help='One or more AWS instances by name or ID')
    snapshot_remove_parser.set_defaults(func='_handle_snapshot_remove')

    # snapshot show subcommand
    snapshot_show_parser = snapshot_subparsers.add_parser('show', help='Show the current snapshot')
    snapshot_show_parser.set_defaults(func='_handle_snapshot_show')

    # --- Command Methods ---
    # These 'do_*' methods will be copied onto the main shell instance.
    @cmd2.with_argparser(snapshot_parser)
    def do_snapshot(self, args: argparse.Namespace) -> None:
        """Category command for AWS snapshot management."""
        # If a subcommand was used, args.func will be set by set_defaults()
        if hasattr(args, 'func'):
            # Get the handler method from this class by its name and call it
            handler = getattr(self, args.func)
            handler(args)
        else:
            # No subcommand was provided, so print the help for the main 'snapshot' command
            self._shell.poutput(self.snapshot_parser.format_help())

    def _handle_snapshot_create(self, args: argparse.Namespace):
        """Add one or more instances to the current target snapshot."""
        
        self._instance_snapshot.add_instances(args.instances)

    def _handle_snapshot_remove(self, args: argparse.Namespace):
        """Remove one or more instances from the current target snapshot."""
        self._instance_snapshot.remove_instances(args.instances)
        self._shell.poutput(f"Removed: {', '.join(args.instances)}")
        

    def _handle_snapshot_show(self, args: argparse.Namespace):
        """Show the instances currently in the target snapshot."""
        targets = self._instance_snapshot.get_instance_objects()
        if not targets:
            self._shell.poutput("No instances are currently in the target snapshot.")
        else:
            output = "Current target instances:\n"
            for inst in sorted(list(targets), key=lambda i: i.name):
                output += f"  - {inst.name} ({inst.id})\n"
            self._shell.poutput(output)



