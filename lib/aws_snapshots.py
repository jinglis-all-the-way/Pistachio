#!/usr/bin/env python

import boto3
import asyncio
import aioboto3
import argparse
import json
from botocore.exceptions import ClientError
import time
import logging
from typing import List, Optional, Dict, Any

class AwsSnapshot:
    def __init__(self, snapshot_id: str, target_instance: str):
       self.snapshot_id = snapshot_id
       self.target_instance = target_instance
       
    def create(self):
        
    def remove(self):
        
    def 
