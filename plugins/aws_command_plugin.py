# plugins/aws_plugin.py

import boto3
import asyncio
import aioboto3
import logging
import json
import time
from botocore.exceptions import ClientError
from typing import List, Optional, Dict, Any, Set

# Import BasePlugin from the main shell file
from TacoShell import BasePlugin

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


class AWSPlugin(BasePlugin):
    """
    A plugin that provides all functionality for interacting with AWS EC2
    instances via SSM.
    """
    def __init__(self, use_async=True, initial_instances=None):
        self.use_async = use_async
        self.instance_group = InstanceGroup(initial_instances=initial_instances)
        self.command_handler = AsyncCommandHandler() if use_async else SimpleCommandHandler()

    @property
    def name(self) -> str:
        return "aws"

    @property
    def commands(self) -> dict:
        """Returns the 'group' command dictionary to be merged into the shell."""
        return {
            'group': {
                '_description': 'Manage the AWS EC2 instance group.',
                'add': self.instance_group.add_instances,
                'remove': self.instance_group.remove_instances,
                'show': self._show_targets,
                'save': self._save_group,
                'load': self._load_group,
                'check-health': self._check_group_health,
            }
        }

    def default_handler(self, command_string: str):
        """
        This method is called by the shell for any command that is not
        a built-in command. It handles remote execution.
        """
        print(f"'{command_string.split()[0]}' is not a built-in command. Passing to AWS command handler...")
        targets = self.instance_group.get_instances()
        if self.use_async:
            asyncio.run(self.command_handler.execute_distributable_command(command_string, targets))
        else:
            self.command_handler.execute_distributable_command(command_string, targets)

    # All helper methods required by the commands now live inside the plugin
    def _show_targets(self, *args):
        targets = self.instance_group.get_instance_objects()
        if not targets:
            print("No instances are currently in the target group.")
        else:
            print("Current target instances:")
            for inst in sorted(list(targets), key=lambda i: i.name):
                print(f"  - {inst.name} ({inst.id})")
        
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
