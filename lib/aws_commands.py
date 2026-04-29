#!/usr/bin/env python



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
            logging.error(f"Execution failed: Could not send command '{command_string}'.")\
 
