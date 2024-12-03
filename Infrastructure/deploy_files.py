from pathlib import Path
import sys
import boto3
import paramiko
import os
import json
from scp import SCPClient

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from constants import AWS_CREDENTIALS_FILE, PRIVATE_KEY_FILE, REGION, REMOTE_APP_PATH, REMOTE_AWS_CREDENTIALS_PATH, LOCAL_PROXY_PATH

def create_ssh_client(instance_dns):
    """Create an SSH client to connect to the instance."""
    key = paramiko.RSAKey.from_private_key_file(str(PRIVATE_KEY_FILE))
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {instance_dns}...")
    ssh.connect(hostname=instance_dns, username='ubuntu', pkey=key)
    return ssh

def run_commands(instance_dns, commands):
    ssh = None
    try:
        ssh = create_ssh_client(instance_dns)
        for command in commands:
            print(f"Executing: {command}")
            stdin, stdout, stderr = ssh.exec_command(command)
            
            # Read command output
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if error:
                print(f"Error executing {command}: {error}")
            else:
                print(f"Executed: {command} Output: {output}")
    except Exception as e:
        print(f"Failed to run commands {instance_dns}: {str(e)}")
    finally:
        if ssh:
            ssh.close()

def deploy_script_via_scp(instance_dns, local_app_path):
    """Use SCP to copy the local script to the remote instance."""
    ssh = None
    try:
        # Create SSH client
        ssh = create_ssh_client(instance_dns)
        
        # SCP the file to the remote instance
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(local_app_path, REMOTE_APP_PATH)
            print(f"Successfully copied {local_app_path} to {instance_dns}:{REMOTE_APP_PATH}")
        
    except Exception as e:
        print(f"Failed to deploy script via scp {instance_dns}: {str(e)}")
    finally:
        if ssh:
            ssh.close()
        
def setup_aws_credentials(instance_dns):
    ssh = None
    try:
        ssh = create_ssh_client(instance_dns)

        # Create the .aws directory, upload credentials, and set file permissions
        commands = [
            "mkdir -p /home/ubuntu/.aws",  # Create .aws directory
        ]
        
        for command in commands:
            print(f"Executing: {command}")
            stdin, stdout, stderr = ssh.exec_command(command)
            print(stderr.read().decode())

        # SCP the credentials file to the remote instance
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(AWS_CREDENTIALS_FILE, REMOTE_AWS_CREDENTIALS_PATH)
            print(f"Successfully copied AWS credentials to {REMOTE_AWS_CREDENTIALS_PATH}")
            
        # Change the file permissions for the credentials file
        ssh.exec_command(f"chmod 600 {REMOTE_AWS_CREDENTIALS_PATH}")
        print(f"File permissions set for {REMOTE_AWS_CREDENTIALS_PATH}")

    except Exception as e:
        print(f"Failed to setup aws credentials {str(e)}")
    finally:
        if ssh:
            ssh.close()

def set_env_variables(instance_dns, env_var_map):
    """Updates the environment variables file on a remote instance. and values are their corresponding values."""
    # Convert the environment variables to a JSON string
    json_content = json.dumps(env_var_map, indent=4)
    
    # Escape the JSON content for safe echoing into the file
    escaped_json_content = json_content.replace('"', '\\"').replace('$', '\\$')
    
    # Commands to create the prod.json file in JSON format
    commands = [
        "rm -f /home/ubuntu/prod.json",
        f"echo \"{escaped_json_content}\" > /home/ubuntu/prod.json"
    ]
    
    # Execute commands on the remote instance
    run_commands(instance_dns, commands)

def proxy_setup(proxy_manager_and_workers_result):
    proxy_dns = proxy_manager_and_workers_result["proxy"]["dns"]
    
    setup_aws_credentials(proxy_dns)

    env_var_map = {
        "MANAGER_DNS": proxy_manager_and_workers_result["manager"]["dns"],
        "WORKER_1_DNS": proxy_manager_and_workers_result["workers"][0]["dns"],
        "WORKER_2_DNS": proxy_manager_and_workers_result["workers"][1]["dns"],
    }
    set_env_variables(proxy_dns, env_var_map)

    deploy_script_via_scp(proxy_dns, LOCAL_PROXY_PATH)

    # install dependencies and run proxy program
    commands = [
        "sudo apt update -y",
        "sudo apt install python3 python3-pip -y",
        "kill -9 $(lsof -t -i :9999)",
        "python3 /home/ubuntu/app.py > /home/ubuntu/app.log 2>&1 &"
    ]
    run_commands(proxy_dns, commands)

def database_instance_setup(instance_dns):
    commands = [
        # install mysql
        "sudo apt-get update -y",
        "sudo apt-get install mysql-server -y",
        # install sakila database
        "wget -N https://downloads.mysql.com/docs/sakila-db.tar.gz",
        "tar -xvzf sakila-db.tar.gz",
        "sudo mysql -u root -e 'CREATE DATABASE sakila;'",
        "sudo mysql -u root sakila < sakila-db/sakila-schema.sql",
        "sudo mysql -u root sakila < sakila-db/sakila-data.sql",
        # install sysbench
        "sudo apt-get install sysbench -y",
        "sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user=root prepare",
        "sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user=root run",
    ]
    run_commands(instance_dns, commands)

def manager_and_workers_setup(proxy_manager_and_workers_result):
    print("Starting manager setup")
    database_instance_setup(proxy_manager_and_workers_result["manager"]["dns"])
    print("Starting worker 1 setup")
    database_instance_setup(proxy_manager_and_workers_result["workers"][0]["dns"])
    print("Starting worker 2 setup")
    database_instance_setup(proxy_manager_and_workers_result["workers"][1]["dns"])

def deploy_files(proxy_manager_and_workers_result):
    manager_and_workers_setup(proxy_manager_and_workers_result)
    print("Finished manager and workers setup")
    proxy_setup(proxy_manager_and_workers_result)
    print("Finished proxy setup")
