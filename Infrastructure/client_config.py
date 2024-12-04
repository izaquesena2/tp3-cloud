import boto3
from botocore.exceptions import ClientError
import os
from pathlib import Path

from constants import KEY_PAIR_NAME, REGION

def create_client():
    return boto3.client('ec2', region_name=REGION)

# Create Key Pair
def create_key_pair(ec2_client):
    try:
        response_key_pair = ec2_client.create_key_pair(KeyName=KEY_PAIR_NAME)
        print(f"KEY PAIR ({response_key_pair['KeyPairId']}) created: {response_key_pair['KeyName']}")
        
        # Save the private key to a file
        private_key = response_key_pair['KeyMaterial']
        key_file_path = Path(f'./{KEY_PAIR_NAME}.pem').resolve()
        with open(key_file_path, 'w') as key_file:
            key_file.write(private_key)
        
        # Set appropriate permissions for the key file (Unix-based systems)
        os.chmod(key_file_path, 0o400)
        return KEY_PAIR_NAME
    except ClientError as e:

        if "InvalidKeyPair.Duplicate" in str(e):
            print(f"Key pair '{KEY_PAIR_NAME}' already exists.")
            return KEY_PAIR_NAME
        else:
            print(f"Error creating key pair: {e}")
            return None