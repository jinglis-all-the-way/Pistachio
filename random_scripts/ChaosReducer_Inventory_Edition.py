import boto3
import csv
from datetime import datetime

def get_all_ec2_instances():
    """
    Fetches all EC2 instances from the AWS account and handles pagination.
    
    Returns:
        A list of all instance dictionary objects from the Boto3 response.
    """
    print("Connecting to AWS and fetching all EC2 instances...")
    try:
        ec2_client = boto3.client('ec2')
        # Use a paginator for describe_instances to handle large numbers of instances
        paginator = ec2_client.get_paginator('describe_instances')
        pages = paginator.paginate()
        
        all_instances = []
        for page in pages:
            for reservation in page['Reservations']:
                all_instances.extend(reservation['Instances'])
        
        print(f"Successfully fetched data for {len(all_instances)} instances.")
        return all_instances
        
    except Exception as e:
        print(f"Error fetching EC2 instances: {e}")
        return []

def flatten_instance_data(instance):
    """
    Takes a single instance dictionary from the Boto3 response and
    flattens it into a simple dictionary suitable for a CSV row.
    
    Args:
        instance: A dictionary representing one EC2 instance.
        
    Returns:
        A flattened dictionary with simple key-value pairs.
    """
    # Helper to extract the 'Name' tag from the Tags list
    name = 'N/A'
    for tag in instance.get('Tags', []):
        if tag['Key'] == 'Name':
            name = tag['Value']
            break

    # Helper to format complex list data into a single string for Excel
    # Example: Security Groups are a list of dicts. We'll join their names.
    security_groups = [sg['GroupName'] for sg in instance.get('SecurityGroups', [])]
    security_groups_str = "; ".join(security_groups) # Use a semicolon as a separator

    # Format the launch time to a more readable string
    launch_time = instance.get('LaunchTime', '')
    if isinstance(launch_time, datetime):
        launch_time_str = launch_time.strftime('%Y-%m-%d %H:%M:%S %Z')
    else:
        launch_time_str = str(launch_time)

    # The flattened data for a single CSV row
    return {
        'Instance ID': instance.get('InstanceId', 'N/A'),
        'Name': name,
        'State': instance.get('State', {}).get('Name', 'N/A'),
        'Instance Type': instance.get('InstanceType', 'N/A'),
        'Public IP Address': instance.get('PublicIpAddress', ''),
        'Private IP Address': instance.get('PrivateIpAddress', ''),
        'VPC ID': instance.get('VpcId', 'N/A'),
        'Subnet ID': instance.get('SubnetId', 'N/A'),
        'Image ID': instance.get('ImageId', 'N/A'),
        'Key Name': instance.get('KeyName', 'N/A'),
        'Platform': instance.get('PlatformDetails', 'Linux/UNIX'),
        'Architecture': instance.get('Architecture', 'N/A'),
        'Launch Time': launch_time_str,
        'Security Groups': security_groups_str,
    }

def main():
    """
    Main function to run the export process.
    """
    all_instances = get_all_ec2_instances()
    
    if not all_instances:
        print("No instances to process. Exiting.")
        return
        
    # Process all instances into a list of flat dictionaries
    processed_data = [flatten_instance_data(inst) for inst in all_instances]
    
    # Define the output file and the headers
    csv_file_name = 'ec2_instances_export.csv'
    headers = [
        'Instance ID', 'Name', 'State', 'Instance Type', 'Public IP Address',
        'Private IP Address', 'VPC ID', 'Subnet ID', 'Image ID', 'Key Name',
        'Platform', 'Architecture', 'Launch Time', 'Security Groups'
    ]
    
    print(f"Writing data to '{csv_file_name}'...")
    
    try:
        with open(csv_file_name, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            
            # Write the header row
            writer.writeheader()
            
            # Write all the instance data rows
            writer.writerows(processed_data)
            
        print(f"\nSuccessfully exported data to '{csv_file_name}'.")
        print("The file is formatted to be opened directly in Microsoft Excel.")
        
    except Exception as e:
        print(f"\nError writing to CSV file: {e}")

if __name__ == '__main__':
    main()

