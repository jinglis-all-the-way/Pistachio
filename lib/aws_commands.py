#!/usr/bin/env python

import boto3
import argparse
import json
from botocore.exceptions import ClientError
import time
import logging
from typing import List, Optional, Dict, Any

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


