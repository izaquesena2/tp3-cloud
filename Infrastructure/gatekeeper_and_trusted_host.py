from pathlib import Path
import sys
import boto3
from botocore.exceptions import ClientError
import os

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from constants import KEY_PAIR_NAME, GATEKEEPER_SECURITY_GROUP_NAME, GATEKEEPER_SECURITY_GROUP_DESCRIPTION, TRUSTED_HOST_SECURITY_GROUP_NAME, TRUSTED_HOST_SECURITY_GROUP_DESCRIPTION

# Create Security Group
def create_security_group(ec2_client, security_group_name, security_group_description):
    try:
        response_security_group = ec2_client.create_security_group(
            GroupName=security_group_name, Description=security_group_description
        )
        security_group_id = response_security_group["GroupId"]
        print(f"Security Group ({security_group_id}) created: {security_group_id}")
        return security_group_id, True

        
    except ClientError as e:
        if "InvalidGroup.Duplicate" in str(e):
            return get_existing_security_group(ec2_client, security_group_name), False
        else:
            print(f"Error creating security group: {e}")
            return None, False

def add_inbound_rules(ec2_client, security_group_name, gatekeeper_security_group_id, trusted_host_security_group_id):
    if security_group_name == GATEKEEPER_SECURITY_GROUP_NAME:
        ec2_client.authorize_security_group_ingress(
            GroupId=gatekeeper_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8000,
                    "ToPort": 8000,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # Allow traffic on 8000 from anywhere
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # Allow SSH from anywhere (optional, restrict as needed)
                },
            ],
        )

    elif security_group_name == TRUSTED_HOST_SECURITY_GROUP_NAME:
        ec2_client.authorize_security_group_ingress(
            GroupId=trusted_host_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8000,
                    "ToPort": 8000,
                    "UserIdGroupPairs": [{"GroupId": gatekeeper_security_group_id}], # Allow traffic only from gatekeeper
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # Allow SSH from anywhere (optional, restrict as needed)
                },
            ],
        )

    else:
        print(f"Invalid security group name: {security_group_name}")

            
def get_existing_security_group(ec2_client, security_group_name):
    try:
        response = ec2_client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [security_group_name]}]
        )
        security_group_id = response["SecurityGroups"][0]["GroupId"]
        print(f"Security Group ({security_group_id}) already exists.")
        return security_group_id

    except ClientError as describe_error:
        print(f"Error retrieving existing security group: {describe_error}")
        security_group_id = None

def get_existing_instances(ec2_client, security_group_id):
    # Fetch running instances for a specific security group.
    response = ec2_client.describe_instances(
        Filters=[
            {"Name": "instance.group-id", "Values": [security_group_id]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    instances = [
        instance["InstanceId"]
        for reservation in response["Reservations"]
        for instance in reservation["Instances"]
    ]
    return instances

def tag_instances(ec2_client, instance_ids, tags):
    ec2_client.create_tags(
        Resources=instance_ids,
        Tags=[{"Key": key, "Value": value} for key, value in tags.items()]
    )

def launch_instances(ec2_client, gatekeeper_security_group_id, trusted_host_security_group_id):
    
    # Parameters for EC2 Instances
    gatekeeper_instance_params = {
        "ImageId": "ami-0e86e20dae9224db8",
        "InstanceType": "t2.large",
        "MinCount": 1,
        "MaxCount": 1,
        "KeyName": KEY_PAIR_NAME,
        "SecurityGroupIds": [gatekeeper_security_group_id],
        "BlockDeviceMappings": [
            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8, "VolumeType": "gp3"}}
        ],
        "Monitoring": {"Enabled": True}, 
    }

    trusted_host_instance_params = {
        "ImageId": "ami-0e86e20dae9224db8",
        "InstanceType": "t2.large",
        "MinCount": 1,
        "MaxCount": 1,
        "KeyName": KEY_PAIR_NAME,
        "SecurityGroupIds": [trusted_host_security_group_id],
        "BlockDeviceMappings": [
            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8, "VolumeType": "gp3"}}
        ],
        "Monitoring": {"Enabled": True}, 
    }

    # Gatekeeper Instance
    gatekeeper_id = get_existing_instances(ec2_client, gatekeeper_security_group_id)
    if not gatekeeper_id:
        print("Launching Gatekeeper Instance...")
        gatekeeper_response = ec2_client.run_instances(**gatekeeper_instance_params)
        gatekeeper_id = gatekeeper_response["Instances"][0]["InstanceId"]
        print(f"Gatekeeper Instance Launched: {gatekeeper_id}")
        tag_instances(ec2_client, [gatekeeper_id], {"Name": "Gatekeeper Instance"})
        waiter = ec2_client.get_waiter('instance_running')
        print(f"Waiting for {gatekeeper_id} instances to be running...")
        waiter.wait(InstanceIds=[gatekeeper_id])
        print(f"{gatekeeper_id} instances are now running.")

    # Trusted Host Instance
    trusted_host_id = get_existing_instances(ec2_client, trusted_host_security_group_id)
    if not trusted_host_id:
        print("Launching Trusted Host Instance...")
        trusted_host_response = ec2_client.run_instances(**trusted_host_instance_params)
        trusted_host_id = trusted_host_response["Instances"][0]["InstanceId"]
        print(f"Trusted Host Instance Launched: {trusted_host_id}")
        tag_instances(ec2_client, [trusted_host_id], {"Name": "Trusted Host Instance"})
        waiter = ec2_client.get_waiter('instance_running')
        print(f"Waiting for {trusted_host_id} instances to be running...")
        waiter.wait(InstanceIds=[trusted_host_id])
        print(f"{trusted_host_id} instances are now running.")

    # Retrieve Public DNS
    gatekeeper_id = gatekeeper_id[0] if isinstance(gatekeeper_id, list) and gatekeeper_id else gatekeeper_id
    trusted_host_id = trusted_host_id[0] if isinstance(trusted_host_id, list) and trusted_host_id else trusted_host_id

    # Retrieve Public DNS
    all_instance_ids = []
    if gatekeeper_id:
        all_instance_ids.append(gatekeeper_id)
    if trusted_host_id:
        all_instance_ids.append(trusted_host_id)

    instances_info = ec2_client.describe_instances(InstanceIds=all_instance_ids)

    dns_mapping = {}
    for reservation in instances_info["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]
            public_dns = instance.get("PublicDnsName", "")
            dns_mapping[instance_id] = public_dns

    # Organize DNS Mapping by Role
    result = {
        "gatekeeper": {"id":gatekeeper_id, "dns":dns_mapping[gatekeeper_id]},
        "trusted_host": {"id":trusted_host_id, "dns":dns_mapping[trusted_host_id]},
    }

    return result
        
def create_gatekeeper_and_trusted_host(ec2_client):
    # create or get security groups
    gatekeeper_security_group_id, check_created = create_security_group(ec2_client, GATEKEEPER_SECURITY_GROUP_NAME, GATEKEEPER_SECURITY_GROUP_DESCRIPTION)
    trusted_host_security_group_id, check_created = create_security_group(ec2_client, TRUSTED_HOST_SECURITY_GROUP_NAME, TRUSTED_HOST_SECURITY_GROUP_DESCRIPTION)

    # add inbound rules
    if check_created:
        add_inbound_rules(ec2_client, GATEKEEPER_SECURITY_GROUP_NAME, gatekeeper_security_group_id, trusted_host_security_group_id)
        add_inbound_rules(ec2_client, TRUSTED_HOST_SECURITY_GROUP_NAME, gatekeeper_security_group_id, trusted_host_security_group_id)

    # Launch EC2 Instances
    result = launch_instances(ec2_client, gatekeeper_security_group_id, trusted_host_security_group_id)
    print(f"Succesfully launched instances gatekeeper and trusted host result={result}")
    return result
        