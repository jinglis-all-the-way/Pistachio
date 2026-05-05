#!/usr/bin/env python

import boto3
import argparse
import json
from botocore.exceptions import ClientError
import time
import logging
from typing import List, Optional, Dict, Any, Set

class AwsEnviroment:
    def __init__(self, ec2_client=None):
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        self.available_instances = list[str]

    def get_all_instance_identifiers() -> list[str]:
        """
        Scans EC2 to find all running or pending instances and returns a list
        of their identifiers (both Instance ID and Name tag).

        Returns:
            A list of strings, where each string is an Instance ID or a Name tag.
            Returns an empty list if an error occurs.
        """
        try:
            ec2_client = boto3.client('ec2')
            
            # A paginator automatically handles API calls to fetch all results
            # when there are more items than a single call can return.
            paginator = ec2_client.get_paginator('describe_instances')

            # This creates an iterable that will yield each page of results.
            pages = paginator.paginate()

            all_identifiers = set()

            # We must loop through pages, then reservations, then instances.
            for page in pages:
                for reservation in page.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        # Add the unique Instance ID
                        if 'InstanceId' in instance:
                            all_identifiers.add(instance['InstanceId'])
            
            return list(all_identifiers)

        except ClientError as e:
            print(f"An AWS API error occurred: {e}")
            return []
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return []

class AwsEc2Instance:
    def __init__(self, identifier: str, ec2_client=None, ssm_client=None):
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        self.ssm_client = ssm_client if ssm_client is not None else boto3.client('ssm')
        self.identifier = identifier
        self.description = None
        self.iid = None
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
            self.iid = self.description.get('InstanceId')
            return True 
        except ClientError as e:
            logging.error(f"AWS API error resolving '{self.identifier}': {e}")
            return False

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def is_ready_for_ssm(self) -> bool:
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
            
        return self.iid

    def get_name(self) -> Optional[str]:
        if not self._is_valid or not self.description:
            return None
        
        instance_name = self.get_id() # Default to ID
        for tag in self.description.get('Tags', []):
            if tag.get('Key') == 'Name' and tag.get('Value'):
                instance_name = tag.get('Value')
                break
        return instance_name

    def get_root_volume_id(self) -> Optional[str]:
        if not self._is_valid or not self.description:
            return None

        root_device_name = self.description['RootDeviceName']

        for mapping in self.description.get('BlockDeviceMappings', []):
            if mapping['DeviceName'] == root_device_name:
                return mapping['Ebs']['VolumeId']
            
        return None
    
    
        
class StrippedAwsInstance:
    def __init__(self, possible_identifier: str, ec2_client=None):
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        self.possible_identifier
        self.source_instance = AwsEc2Instance(identifier=self.possible_identifier, ec2_client=self.ec2_client)
        self.id = None  
        self.name = None
        self.is_valid = False

    # --- Essential methods for list/set operations ---
    def __eq__(self, other):
        if not isinstance(other, __class__):
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
            return hash(self.possible_identifier)

    def __repr__(self):
        if self.is_valid:
            return f"{__class__}(id='{self.id}', name='{self.name}')"
        else:
            return f"{__class__}(invalid_identifier='{self.possible_identifier}')"

            
class InstanceGroup:
    def __init__(self, ec2_client=None, initial_instances: Optional[List[str]] = None): 
        logging.debug("Created new InstanceGroup object")
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        self._instances: Set[StrippedAwsInstance] = set()
        
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

    def get_instance_objects(self) -> Set['StrippedAwsInstance']:
        """Returns the set of stored StrippedAwsInstance objects for display."""
        return self._instances
           
