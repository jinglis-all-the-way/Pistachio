import boto3
from botocore.exceptions import ClientError
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class Ec2InstanceData:
    """
    An immutable dataclass to hold comprehensive data for a single EC2 instance.
    """
    # --- Core Identification ---
    instance_id: str
    image_id: str
    instance_type: str
    
    # --- State and Lifecycle ---
    state: str  # e.g., 'running', 'stopped', 'terminated'
    launch_time: datetime
    
    # --- Naming and Tagging ---
    tags: Dict[str, str] = field(default_factory=dict)
    
    # --- Networking ---
    vpc_id: Optional[str]
    subnet_id: Optional[str]
    private_ip: Optional[str]
    public_ip: Optional[str]
    network_interfaces: List[Dict[str, Any]] = field(default_factory=list)

    # --- Platform and Architecture ---
    architecture: str
    platform: str  # e.g., 'windows' or 'linux/unix'
    
    # --- Security ---
    key_name: Optional[str]
    security_groups: List[Dict[str, str]] = field(default_factory=list)

    # --- Block Storage ---
    block_device_mappings: List[Dict[str, Any]] = field(default_factory=list)
    root_device_name: Optional[str]
    
    @property
    def name(self) -> str:
        """A convenient property to get the instance's 'Name' tag."""
        return self.tags.get('Name', 'N/A')

    def to_dict(self) -> dict:
        """A standard method to serialize the data to a dictionary."""
        return asdict(self)

class InstanceLoader:
    """
    Loads EC2 instance data from AWS and populates an Ec2InstanceData object.
    """
    def __init__(self, ec2_client=None):
        """
        Initializes the loader. An existing Boto3 client can be injected for testing.
        """
        self.ec2_client = ec2_client or boto3.client('ec2')

    def load(self, instance_id: str) -> Optional[Ec2InstanceData]:
        """
        Fetches data for a single EC2 instance and returns a populated dataclass.
        Returns None if the instance is not found or an error occurs.
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            
            # The API returns a nested structure. We need to get the actual instance dict.
            reservations = response.get('Reservations', [])
            if not reservations or not reservations[0].get('Instances'):
                print(f"Warning: No instance found with ID '{instance_id}'.")
                return None
            
            instance_dict = reservations[0]['Instances'][0]
            
            # --- Parse the data and populate the dataclass ---
            return self._parse_instance_dict(instance_dict)

        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                print(f"Warning: No instance found with ID '{instance_id}'.")
            else:
                print(f"An AWS client error occurred: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None

    def _parse_instance_dict(self, instance_dict: Dict[str, Any]) -> Ec2InstanceData:
        """
        Private helper method to transform the Boto3 dict into our dataclass.
        """
        # Helper to parse tags from a list of dicts to a simple dict
        tags = {tag['Key']: tag['Value'] for tag in instance_dict.get('Tags', [])}
        
        # Determine the platform details
        platform = instance_dict.get('Platform', 'linux/unix').capitalize()
        if 'PlatformDetails' in instance_dict:
            platform = instance_dict['PlatformDetails']

        # Create and return the populated dataclass
        data = Ec2InstanceData(
            instance_id=instance_dict.get('InstanceId'),
            image_id=instance_dict.get('ImageId'),
            instance_type=instance_dict.get('InstanceType'),
            state=instance_dict.get('State', {}).get('Name'),
            launch_time=instance_dict.get('LaunchTime'),
            tags=tags,
            vpc_id=instance_dict.get('VpcId'),
            subnet_id=instance_dict.get('SubnetId'),
            private_ip=instance_dict.get('PrivateIpAddress'),
            public_ip=instance_dict.get('PublicIpAddress'),
            network_interfaces=instance_dict.get('NetworkInterfaces', []),
            architecture=instance_dict.get('Architecture'),
            platform=platform,
            key_name=instance_dict.get('KeyName'),
            security_groups=instance_dict.get('SecurityGroups', []),
            block_device_mappings=instance_dict.get('BlockDeviceMappings', []),
            root_device_name=instance_dict.get('RootDeviceName'),
        )
        return data

