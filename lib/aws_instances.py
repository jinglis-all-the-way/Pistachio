#!/usr/bin/env python

import boto3
import argparse
import json
from botocore.exceptions import ClientError
import time
import logging
from typing import List, Optional, Dict, Any, Set

class AwsInstance:
    def __init__(self, identifier: str, ec2_client=None):
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
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

        if heavy_instance.is_valid:
            self.id = heavy_instance.get_id()
            self.name = heavy_instance.get_name()
            self.is_valid = heavy_instance.is_valid

    @property
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
        self.instances: Set[StrippedAwsInstance] = set()
        logging.debug("Created new InstanceGroup object")
        logging.debug(f"{type(self.instances)}")
        if initial_instances:
            self.add_instances(initial_instances)

    def add_instances(self, instance_list: List[str]):
        if not instance_list:
            logging.warning("No instances specified to add")
            return
        for item in instance_list:
            this_instance = StrippedAwsInstance(ec2_client=self.ec2_client, possible_identifier=item)
            if this_instance.is_valid:
                found_names_and_ids = {inst.name for inst in instances_to_keep} | {inst.id for inst in instances_to_keep}
                if this_instance not in found_names_and_ids:
                    logging.debug(f"{type(self.instances)}")
                    self.instances.add(this_instance)
                    print(f"Added instance '{this_instance.name}' ({this_instance.id}) to group.")
                else:
                    logging.warning(f"Unable to add '{item}' since it is already there")
                    print(f"Instance '{item}' already in group")
            else:
                logging.warning(f"'{item}' is not a valid instance")
                print(f"Warning : '{item}' is not a valid instance, therefore it will not be added to the group")

    def remove_instances(self, removal_set: Set[str]):
        if not removal_set:
            logging.warning("No instances specified to remove.")
            return
        
        instances_to_keep = [
            inst for inst in self.instances 
            if inst.name not in removal_set and inst.id not in removal_set
        ]
        
        removed_count = len(self.instances) - len(instances_to_keep)
        original_count = len(self.instances)

        # Log warnings for items in the removal list that were not found
        found_names_and_ids = {inst.name for inst in instances_to_keep} | {inst.id for inst in instances_to_keep}
        for item in removal_set:
            if item not in found_names_and_ids:
                 logging.warning(f"'{item}' not found in instance group and could not be removed.")
                 print(f"'{item}' is not part of this group")

        logging.info(f"Removed {removed_count} instances. Original count: {original_count}, New count: {len(instances_to_keep)}.")
        print(f"Removed {removed_count} instances from the group.")
        
        self.instances = instances_to_keep
                

    def get_instances(self) -> Dict[str, str]:
        return {inst.id: inst.name for inst in self.instances if inst.id}
           
