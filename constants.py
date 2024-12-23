from pathlib import Path

KEY_PAIR_NAME = 'tp3-key-pair'
PRIVATE_KEY_FILE = Path(f'./{KEY_PAIR_NAME}.pem').resolve()
WORKER_SECURITY_GROUP_NAME = 'tp3-worker-security-group-name'
WORKER_SECURITY_GROUP_DESCRIPTION = 'tp3-worker-security-group-description'
MANAGER_SECURITY_GROUP_NAME = 'tp3-manager-security-group-name'
MANAGER_SECURITY_GROUP_DESCRIPTION = 'tp3-manager-security-group-description'
PROXY_SECURITY_GROUP_NAME = 'tp3-proxy-security-group-name'
PROXY_SECURITY_GROUP_DESCRIPTION = 'tp3-proxy-security-group-description'
GATEKEEPER_SECURITY_GROUP_NAME = 'tp3-gatekeeper-security-group-name'
GATEKEEPER_SECURITY_GROUP_DESCRIPTION = 'tp3-gatekeeper-security-group-description'
TRUSTED_HOST_SECURITY_GROUP_NAME = 'tp3-trusted-host-security-group-name'
TRUSTED_HOST_SECURITY_GROUP_DESCRIPTION = 'tp3-trusted-host-security-group-description'


# Application script paths
LOCAL_PROXY_PATH = Path('./Application/proxy.py').resolve()
LOCAL_WORKER_PATH = Path('./Application/worker.py').resolve()
LOCAL_MANAGER_PATH = Path('./Application/manager.py').resolve()
LOCAL_GATEKEEPER_PATH = Path('./Application/gatekeeper.py').resolve()
LOCAL_TRUSTED_HOST_PATH = Path('./Application/trusted_host.py').resolve()
REMOTE_APP_PATH = "/home/ubuntu/app.py"  # Remote path for all scripts

AWS_CREDENTIALS_FILE = Path('~/.aws/credentials').expanduser().resolve()  # Local AWS credentials file path
REMOTE_AWS_CREDENTIALS_PATH = "/home/ubuntu/.aws/credentials" 
REGION = "us-east-1"
