# plugins/aws_plugin.py

import argparse
import asyncio
import boto3
# ... other imports from aws_lib ...

# Import BasePlugin from the main shell file
from webshell import BasePlugin

# --- (All your AWS classes: AwsInstance, StrippedAwsInstance, InstanceGroup, CommandHandler, etc. go here) ---

class AWSPlugin(BasePlugin):
    """Provides all functionality for interacting with AWS EC2."""
    
    def __init__(self, **kwargs):
        # The plugin now receives its config from the shell's argument parser
        use_async = kwargs.get('mode', 'async') == 'async'
        initial_instances = kwargs.get('instances')

        self._use_async = use_async
        self._instance_group = InstanceGroup(initial_instances=initial_instances)
        self._command_handler = AsyncCommandHandler() if use_async else SimpleCommandHandler()
        
        # Link the shell instance to the plugin instance for poutput access
        # This happens automatically when cmd2 registers the mixin.
        self._shell = None 

    @property
    def name(self) -> str:
        return "aws"

    # ... (The do_group_* methods are the same as the previous version) ...

    def default(self, statement: str):
        """The default handler for executing remote commands via SSM."""
        # ... (implementation is the same, but use self._shell.poutput) ...
        pass
