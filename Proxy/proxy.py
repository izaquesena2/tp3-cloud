import socket
import random
import subprocess
import os
import logging
import json

CONFIG_FILE = "/home/ubuntu/prod.json"

def load_config(file_path):
    """Load configuration from a JSON file."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading configuration file: {e}")
        return {}

config = load_config(CONFIG_FILE)

# Configure logging
logging.basicConfig(
    filename='/home/ubuntu/app.log',  # Log file location
    level=logging.INFO,               # Log level
    format='%(asctime)s - %(message)s'
)

MANAGER_DNS = config.get("MANAGER_DNS")
WORKER_1_DNS = config.get("WORKER_1_DNS")
WORKER_2_DNS = config.get("WORKER_2_DNS")

# Define the MySQL servers using DNS names
MANAGER = (MANAGER_DNS, 3306)
WORKERS = [(WORKER_1_DNS, 3306), (WORKER_2_DNS, 3306)]

# Proxy settings
PROXY_HOST = "0.0.0.0"
PROXY_PORT = 9999  # Port where the proxy listens


def measure_latency(server):
    """Measure the ping latency to a server."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", server[0]], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        time_ms = float(result.stdout.decode().split("time=")[-1].split(" ms")[0])
        return time_ms
    except Exception:
        return float("inf")  # Return high latency if unreachable


def select_worker_random():
    """Select a worker randomly."""
    return random.choice(WORKERS)


def forward_request(client_socket, target_server):
    """Forward the client's request to the target server and send back the response."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.connect(target_server)
            
            # Forward data from client to target server
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break
                server_socket.sendall(data)
            
            # Receive response from the target server
            response = b""
            while True:
                chunk = server_socket.recv(4096)
                if not chunk:
                    break
                response += chunk
            
            client_socket.sendall(response)
        return response.decode()
    except Exception as e:
        logging.info(f"Error forwarding request: {e}")
        return None


def forward_to_workers(request):
    """Forward a write request to all workers."""
    for worker in WORKERS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as worker_socket:
                worker_socket.connect(worker)
                worker_socket.sendall(request.encode())
                worker_socket.recv(4096)  # Optional: Handle worker responses
        except Exception as e:
            logging.info(f"Error forwarding to worker {worker}: {e}")


def main():
    """Main function to run the proxy server."""
    logging.info("Starting proxy")
    logging.info(f"MANAGER_DNS: {MANAGER_DNS}")
    logging.info(f"WORKER_1_DNS: {WORKER_1_DNS}")
    logging.info(f"WORKER_2_DNS: {WORKER_2_DNS}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy_socket:
        proxy_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy_socket.bind((PROXY_HOST, PROXY_PORT))
        proxy_socket.listen(5)
        logging.info(f"Proxy server listening on {PROXY_HOST}:{PROXY_PORT}")
        
        while True:
            client_socket, client_address = proxy_socket.accept()
            logging.info(f"Connection from {client_address}")
            
            try:
                # Parse the incoming request (simplified for demonstration)
                request = client_socket.recv(4096).decode()
                logging.info(f"Received request: {request}")
                
                if "SELECT" in request.upper():
                    # Read request: Route directly to a worker
                    target_server = select_worker_random()
                    logging.info(f"Routing READ request to worker: {target_server}")
                    forward_request(client_socket, target_server)
                
                else:
                    # Write request: Route to manager first
                    logging.info(f"Routing WRITE request to manager: {MANAGER}")
                    manager_response = forward_request(client_socket, MANAGER)
                    
                    if manager_response and "SUCCESS" in manager_response.upper():
                        logging.info("WRITE successful on manager. Propagating to workers...")
                        forward_to_workers(request)
                    else:
                        logging.info("WRITE failed on manager. Not propagating to workers.")
                
            except Exception as e:
                logging.info(f"Error handling client request: {e}")
            finally:
                client_socket.close()


main()
