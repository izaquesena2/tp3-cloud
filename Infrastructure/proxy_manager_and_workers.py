from pathlib import Path
import sys
import boto3
from botocore.exceptions import ClientError
import os

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from constants import KEY_PAIR_NAME, WORKER_SECURITY_GROUP_NAME, WORKER_SECURITY_GROUP_DESCRIPTION, MANAGER_SECURITY_GROUP_NAME, MANAGER_SECURITY_GROUP_DESCRIPTION, PROXY_SECURITY_GROUP_NAME, PROXY_SECURITY_GROUP_DESCRIPTION 

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

def add_inbound_rules(ec2_client, security_group_name, worker_security_group_id, manager_security_group_id, proxy_security_group_id):
    if security_group_name == WORKER_SECURITY_GROUP_NAME:
        ec2_client.authorize_security_group_ingress(
            GroupId=worker_security_group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'UserIdGroupPairs': [{'GroupId': proxy_security_group_id}],  # Allow traffic from Proxy SG
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # Allow SSH from anywhere
                },
            ],
        )
    elif security_group_name == MANAGER_SECURITY_GROUP_NAME:
        ec2_client.authorize_security_group_ingress(
            GroupId=manager_security_group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'UserIdGroupPairs': [{'GroupId': proxy_security_group_id}],  # Allow traffic from Proxy SG
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # Allow SSH from anywhere
                },
            ],
        )

    elif security_group_name == PROXY_SECURITY_GROUP_NAME:
        ec2_client.authorize_security_group_ingress(
            GroupId=proxy_security_group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}],  # Allow public access (can restrict this further)
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # Allow SSH from anywhere
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

def launch_instances(ec2_client, worker_security_group_id, manager_security_group_id, proxy_security_group_id):
    
    # Parameters for EC2 Instances
    worker_instance_params = {
        "ImageId": "ami-0e86e20dae9224db8",
        "InstanceType": "t2.micro",
        "MinCount": 2,
        "MaxCount": 2,
        "KeyName": KEY_PAIR_NAME,
        "SecurityGroupIds": [worker_security_group_id],
        "BlockDeviceMappings": [
            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8, "VolumeType": "gp3"}}
        ],
        "Monitoring": {"Enabled": True}, 
    }

    manager_instance_params = {
        "ImageId": "ami-0e86e20dae9224db8",
        "InstanceType": "t2.micro",
        "MinCount": 1,
        "MaxCount": 1,
        "KeyName": KEY_PAIR_NAME,
        "SecurityGroupIds": [manager_security_group_id],
        "BlockDeviceMappings": [
            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8, "VolumeType": "gp3"}}
        ],
        "Monitoring": {"Enabled": True}, 
    }

    proxy_instance_params = {
        "ImageId": "ami-0e86e20dae9224db8",
        "InstanceType": "t2.large",
        "MinCount": 1,
        "MaxCount": 1,
        "KeyName": KEY_PAIR_NAME,
        "SecurityGroupIds": [proxy_security_group_id],
        "BlockDeviceMappings": [
            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8, "VolumeType": "gp3"}}
        ],
        "Monitoring": {"Enabled": True}, 
    }

    # Worker Instances
    worker_ids = get_existing_instances(ec2_client, worker_security_group_id)
    if len(worker_ids) < 2:
        print("Launching Worker Instances...")
        worker_response = ec2_client.run_instances(**worker_instance_params)
        worker_ids = [instance["InstanceId"] for instance in worker_response["Instances"]]
        print(f"Worker Instances Launched: {worker_ids}")
        tag_instances(ec2_client, worker_ids, {"Name": "Worker Instance"})
        waiter = ec2_client.get_waiter('instance_running')
        print(f"Waiting for {worker_ids} instances to be running...")
        waiter.wait(InstanceIds=worker_ids)
        print(f"{worker_ids} instances are now running.")

    # Manager Instance
    manager_id = get_existing_instances(ec2_client, manager_security_group_id)
    if not manager_id:
        print("Launching Manager Instance...")
        manager_response = ec2_client.run_instances(**manager_instance_params)
        manager_id = manager_response["Instances"][0]["InstanceId"]
        print(f"Manager Instance Launched: {manager_id}")
        tag_instances(ec2_client, [manager_id], {"Name": "Manager Instance"})
        waiter = ec2_client.get_waiter('instance_running')
        print(f"Waiting for {manager_id} instances to be running...")
        waiter.wait(InstanceIds=worker_ids)
        print(f"{manager_id} instances are now running.")

    # Proxy Instance
    proxy_id = get_existing_instances(ec2_client, proxy_security_group_id)
    if not proxy_id:
        print("Launching Proxy Instance...")
        proxy_response = ec2_client.run_instances(**proxy_instance_params)
        proxy_id = proxy_response["Instances"][0]["InstanceId"]
        print(f"Proxy Instance Launched: {proxy_id}")
        tag_instances(ec2_client, [proxy_id], {"Name": "Proxy Instance"})
        waiter = ec2_client.get_waiter('instance_running')
        print(f"Waiting for {proxy_id} instances to be running...")
        waiter.wait(InstanceIds=worker_ids)
        print(f"{proxy_id} instances are now running.")

    # Retrieve Public DNS
    manager_id = manager_id[0] if isinstance(manager_id, list) and manager_id else manager_id
    proxy_id = proxy_id[0] if isinstance(proxy_id, list) and proxy_id else proxy_id

    # Retrieve Public DNS
    all_instance_ids = []
    all_instance_ids.extend(worker_ids)
    if manager_id:
        all_instance_ids.append(manager_id)
    if proxy_id:
        all_instance_ids.append(proxy_id)

    instances_info = ec2_client.describe_instances(InstanceIds=all_instance_ids)

    dns_mapping = {}
    for reservation in instances_info["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]
            public_dns = instance.get("PublicDnsName", "")
            dns_mapping[instance_id] = public_dns

    # Organize DNS Mapping by Role
    result = {
        "workers": [{"id":worker_id, "dns":dns_mapping[worker_id]} for worker_id in worker_ids],
        "manager": {"id":manager_id, "dns":dns_mapping[manager_id]},
        "proxy": {"id":proxy_id, "dns":dns_mapping[proxy_id]},
    }

    return result
        
def create_proxy_manager_and_workers(ec2_client):
    # create or get security groups
    worker_security_group_id, check_created = create_security_group(ec2_client, WORKER_SECURITY_GROUP_NAME, WORKER_SECURITY_GROUP_DESCRIPTION)
    manager_security_group_id, check_created = create_security_group(ec2_client, MANAGER_SECURITY_GROUP_NAME, MANAGER_SECURITY_GROUP_DESCRIPTION)
    proxy_security_group_id, check_created = create_security_group(ec2_client, PROXY_SECURITY_GROUP_NAME, PROXY_SECURITY_GROUP_DESCRIPTION)

    # add inbound rules
    if check_created:
        add_inbound_rules(ec2_client, WORKER_SECURITY_GROUP_NAME, worker_security_group_id, manager_security_group_id, proxy_security_group_id)
        add_inbound_rules(ec2_client, MANAGER_SECURITY_GROUP_NAME, worker_security_group_id, manager_security_group_id, proxy_security_group_id)
        add_inbound_rules(ec2_client, PROXY_SECURITY_GROUP_NAME, worker_security_group_id, manager_security_group_id, proxy_security_group_id)

    # Launch EC2 Instances
    result = launch_instances(ec2_client, worker_security_group_id, manager_security_group_id, proxy_security_group_id)
    print(f"Succesfully launched instances proxy, manager an workers result={result}")
    return result
        