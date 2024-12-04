from pathlib import Path
import sys
import boto3
import paramiko
import os
import json
from scp import SCPClient

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from constants import AWS_CREDENTIALS_FILE, PRIVATE_KEY_FILE, REGION, REMOTE_APP_PATH, REMOTE_AWS_CREDENTIALS_PATH, LOCAL_PROXY_PATH, LOCAL_WORKER_PATH, LOCAL_MANAGER_PATH, LOCAL_GATEKEEPER_PATH, LOCAL_TRUSTED_HOST_PATH

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

        # install dependencies and run proxy program
        commands = [
            "sudo apt update -y",
            "sudo apt install python3 python3-pip -y",
            "sudo apt install -y python3-uvicorn",
            "sudo apt install -y python3-fastapi",
            "kill -9 $(lsof -t -i :8000)",
            "python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 > /home/ubuntu/app.log 2>&1 &"
        ]
        run_commands(instance_dns, commands)
        
    except Exception as e:
        print(f"Failed to deploy script via scp {instance_dns}: {str(e)}")
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

    env_var_map = {
        "MANAGER_DNS": proxy_manager_and_workers_result["manager"]["dns"],
        "WORKER_1_DNS": proxy_manager_and_workers_result["workers"][0]["dns"],
        "WORKER_2_DNS": proxy_manager_and_workers_result["workers"][1]["dns"],
    }
    set_env_variables(proxy_dns, env_var_map)

    deploy_script_via_scp(proxy_dns, LOCAL_PROXY_PATH)

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
    print("Starting manager database setup")
    database_instance_setup(proxy_manager_and_workers_result["manager"]["dns"])
    print("Starting worker 1 database setup")
    database_instance_setup(proxy_manager_and_workers_result["workers"][0]["dns"])
    print("Starting worker 2 database setup")
    database_instance_setup(proxy_manager_and_workers_result["workers"][1]["dns"])

    deploy_script_via_scp(proxy_manager_and_workers_result["manager"]["dns"], LOCAL_MANAGER_PATH)
    deploy_script_via_scp(proxy_manager_and_workers_result["workers"][0]["dns"], LOCAL_WORKER_PATH)
    deploy_script_via_scp(proxy_manager_and_workers_result["workers"][1]["dns"], LOCAL_WORKER_PATH)

def gatekeeper_setup(gatekeepr_and_trusted_host_result):
    print("Starting gatekeeper setup")
    gatekeeper_dns = gatekeepr_and_trusted_host_result["gatekeeper"]["dns"]

    env_var_map = {
        "TRUSTED_HOST_DNS": gatekeepr_and_trusted_host_result["trusted_host"]["dns"],
    }
    set_env_variables(gatekeeper_dns, env_var_map)

    deploy_script_via_scp(gatekeeper_dns, LOCAL_GATEKEEPER_PATH)

def trusted_host_setup(proxy_manager_and_workers_result, gatekeepr_and_trusted_host_result):
    print("Starting gatekeeper setup")
    trusted_host_dns = gatekeepr_and_trusted_host_result["trusted_host"]["dns"]

    env_var_map = {
        "PROXY_DNS": proxy_manager_and_workers_result["proxy"]["dns"],
    }
    set_env_variables(trusted_host_dns, env_var_map)

    deploy_script_via_scp(trusted_host_dns, LOCAL_TRUSTED_HOST_PATH)


def deploy_files(proxy_manager_and_workers_result, gatekeepr_and_trusted_host_result):
    # manager_and_workers_setup(proxy_manager_and_workers_result)
    # print("Finished manager and workers setup")
    # proxy_setup(proxy_manager_and_workers_result)
    # print("Finished proxy setup")
    gatekeeper_setup(gatekeepr_and_trusted_host_result)
    print("Finished gatekeeper setup")
    trusted_host_setup(proxy_manager_and_workers_result, gatekeepr_and_trusted_host_result)
    print("Finished trusted host setup")

