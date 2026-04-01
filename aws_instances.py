#!/usr/bin/env python

import boto3
import argparse
import json
from botocore.exceptions import ClientError
import time
import logging
from typing import List, Optional, Dict, Any

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
                        {'Name': 'tag:Name', 'Value': [self.identifier]},
                        {'Name': 'instance-state-name', 'Value': ['running']}
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

    def get_id(self) -> str | None:
        if not self._is_valid or not self.description:
            return None
            
        return self.description.get('InstanceId')

    def get_name(self) -> str | None:
        if not self._is_valid or not self.description:
            return None
        
        instance_name = self.get_id() # Default to ID
        for tag in self.description.get('Tags', []):
            if tag.get('Key') == 'Name' and tag.get('Value'):
                instance_name = tag.get('Value')
                break
        return instance_name
        
class StrippedAwsInstance:
    def __init__(self, identifier: str, ec2_client=None):
        heavy_instance = AwsInstance(identifier, ec2_client)
        
        self.id = None
        self.name = None
        
        if heavy_instance.is_valid:
            self.id = heavy_instance.get_id()
            self.name = heavy_instance.get_name()

    @property
    def is_valid(self) -> bool:
        """An instance is valid if it has an ID."""
        return self.id is not None

    # --- Essential methods for list/set operations ---
    def __eq__(self, other):
        if not isinstance(other, StrippedAwsInstance):
            return NotImplemented
        return self.id is not None and self.id == other.id

    def __hash__(self):
        return hash(self.id)
            
class InstanceGroup:
    def __init__(self, ec2_client=None, ec2_resource=None, initial_instances: Optional[List[str]] = None): 
        self.ec2_resource =  ec2_resource if ec2_resource is not None else boto3.resource('ec2')
        self.ec2_client = ec2_client if ec2_client is not None else boto3.client('ec2')
        self.instances = []
        logging.debug("Created new InstanceGroup object")
        
        if initial_instances:
            self.add_instances(initial_instances)

    def add_instances(self, instance_list: List[str]):
        if not instance_list:
            logging.warning("No instances specified to add")
            return
            
        for item in instance_list:
            this_instance = StrippedAwsInstance(self.ec2_client, self.ec2_resource, item)
            if this_instance.isValid():
                if this_instance not in self.instances
                    logging.info(f"Adding instance to group : '{item}'")
                    self.instances.append(this_instance)
                else:
                    logging.warning(f"Unable to add '{item}' since it is already there")
                    print(f"Instance '{item}' already in group")
            else:
                logging.warning(f"'{item}' is not a valid instance")
                print(f"Warning : '{item}' is not a valid instance, therefore it will not be added to the group")

    def remove_instances(self, removal_list: List[str]):
        if not removal_list:
            logging.warning("No instances specified to remove.")
            return
        
        removal_set = set(removal__list)
        
        
        instances_to_keep = [
            inst for inst in self.instances 
            if inst.name not in removal_set and inst.i_id not in removal_set
        ]
        
        removed_count = len(self.instances) - len(instances_to_keep)
        original_count = len(self.instances)

        # Log warnings for items in the removal list that were not found
        found_names_and_ids = {inst.name for inst in instances_to_keep} | {inst.i_id for inst in instances_to_keep}
        for item in removal_set:
            if item not in found_names_and_ids:
                 logging.warning(f"'{item}' not found in instance group and could not be removed.")
                 print(f"'{item}' is not part of this group")

        logging.info(f"Removed {removed_count} instances. Original count: {original_count}, New count: {len(instances_to_keep)}.")
        print(f"Removed {removed_count} instances from the group.")
        
        self.instances = instances_to_keep
                

    def get_instances(self) -> Dict[str, str]:
        return self.instances
           
