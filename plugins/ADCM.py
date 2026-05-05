# boto3 imports
import boto3
from botocore.exceptions import ClientError

# cmd2 imports
import argparse
import cmd2

# general imports
import json
import time
import logging
from typing import List, Optional, Dict, Any

# local imports
from plugin_interface import BasePlugin
from lib.aws_instances import StrippedAwsInstance, InstanceGroup


class SsmInstance(StrippedAwsInstance):
    def __init__():
        super().__init__()

        if source_instance.is_valid and source_instance.is_ready_for_ssm:
            self.id = source_instance.get_id()
            self.name = source_instance.get_name()
            self.is_valid = True

class SsmInstanceGroup(InstanceGroup):
    def __init__(self, ec2_client=None, initial_instances: Optional[List[str]] = None):
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        super().__init__(ec2_client=self.ec2_client)
        self._instances: Set[SsmInstance] = set()

    def get_instance_objects(self) -> Set[SsmInstance]:
        """Returns the set of stored StrippedAwsInstance objects for display."""
        return self._instances

class SsmCommandHandler():
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

    group_parser = cmd2.Cmd2ArgumentParser(description='Group management. Use this command to add, remove, or show the current target group.\nAll non-builtin commands will be ran on the target group via AWS SSM')
    group_subparsers = group_parser.add_subparsers(title='subcommands', dest='subcommand', help='group subcommands')
    
    # group add subcommand
    group_add_parser = group_subparsers.add_parser('add', help='Adds indicated instances to the target group')
    group_add_parser.add_argument('instances', nargs='+', help='One or more AWS instances by name or ID')
    group_add_parser.set_defaults(func='_handle_group_add')

    # group remove subcommand
    group_remove_parser = group_subparsers.add_parser('remove', help='Removes indicated instances from the target group')
    group_remove_parser.add_argument('instances', nargs='+', help='One or more AWS instances by name or ID')
    group_remove_parser.set_defaults(func='_handle_group_remove')

    # group show subcommand
    group_show_parser = group_subparsers.add_parser('show', help='Show the current group')
    group_show_parser.set_defaults(func='_handle_group_show')

    # --- Command Methods ---
    # These 'do_*' methods will be copied onto the main shell instance.
    @cmd2.with_argparser(group_parser)
    def do_group(self, args: argparse.Namespace) -> None:
        """Category command for AWS group management."""
        # If a subcommand was used, args.func will be set by set_defaults()
        if hasattr(args, 'func'):
            # Get the handler method from this class by its name and call it
            handler = getattr(self, args.func)
            handler(args)
        else:
            # No subcommand was provided, so print the help for the main 'group' command
            self._shell.poutput(self.group_parser.format_help())

    def _handle_group_add(self, args: argparse.Namespace):
        """Add one or more instances to the current target group."""
        
        self._instance_group.add_instances(args.instances)

    def _handle_group_remove(self, args: argparse.Namespace):
        """Remove one or more instances from the current target group."""
        self._instance_group.remove_instances(args.instances)
        self._shell.poutput(f"Removed: {', '.join(args.instances)}")
        

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
            
  