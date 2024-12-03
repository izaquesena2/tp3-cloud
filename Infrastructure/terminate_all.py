import boto3
import logging

# Create an EC2 resource object
ec2_resource = boto3.resource('ec2')

# Set up logging
logging.basicConfig(level=logging.INFO)

def terminate_all_instances():
    # Get a list of all instances
    instances = ec2_resource.instances.all()
    
    for instance in instances:
        instance_id = instance.id
        state = instance.state['Name']
        
        logging.info(f"Instance ID: {instance_id}, Current State: {state}")

        if state in ['running', 'stopped', 'pending', 'stopping']:
            logging.info(f"Terminating instance {instance_id}...")
            instance.terminate()
            instance.wait_until_terminated()
            logging.info(f"Instance {instance_id} terminated.")
        else:
            logging.info(f"Instance {instance_id} is in state {state} and cannot be terminated.")

terminate_all_instances()