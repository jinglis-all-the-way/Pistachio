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
from typing import List, Optional, Dict, Any, Set

# local imports
from plugin_interface import BasePlugin
from lib.aws_instances import StrippedAwsInstance, InstanceGroup