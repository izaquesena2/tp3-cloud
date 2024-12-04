import logging
import json
import random
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

CONFIG_FILE = "/home/ubuntu/prod.json"

def load_config(file_path):
    """Load configuration from a JSON file."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading configuration file: {e}")
        return {}

# Load configuration
config = load_config(CONFIG_FILE)

# Configure logging
logging.basicConfig(
    filename='/home/ubuntu/app.log',  
    level=logging.INFO,              
    format='%(asctime)s - %(message)s'
)

# Define DNS/URLs for Manager and Workers
MANAGER_DNS = f"http://{config.get('MANAGER_DNS')}:8000/run-query"
WORKER_1_DNS = f"http://{config.get('WORKER_1_DNS')}:8000/run-query"
WORKER_2_DNS = f"http://{config.get('WORKER_2_DNS')}:8000/run-query"

# Define request body schema
class QueryRequest(BaseModel):
    query: str

# Define response body schema
class QueryResponse(BaseModel):
    error: int
    stdout: str

# Helper function to send SQL queries to a specific URL
def send_query_to_server(url, query):
    try:
        response = requests.post(url, json={"query": query}, timeout=5)  # Set timeout to avoid hanging
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logging.error(f"Error communicating with server {url}: {e}")
        return None

@app.post("/run-query/", response_model=QueryResponse)
async def run_query(request: QueryRequest):
    query = request.query.strip()
    logging.info(f"query: {query}")
    
    # Determine if the query is READ or WRITE
    if query.lower().startswith("select"):  # READ query
        logging.info(f"read query")
        selected_worker = random.choice([WORKER_1_DNS, WORKER_2_DNS])
        response = send_query_to_server(selected_worker, query)
        logging.info(f"read response: {response}")
        if response and response.status_code == 200:
            return QueryResponse(error=0, stdout=response.json().get("stdout", ""))
        else:
            raise HTTPException(status_code=500, detail="Error from worker")

    elif query.lower().startswith(("insert", "update", "delete")):  # WRITE query
        logging.info(f"write query")
        # Send the query to the MANAGER
        manager_response = send_query_to_server(MANAGER_DNS, query)
        logging.info(f"manager response: {manager_response}")
        
        if manager_response and manager_response.status_code == 200 and manager_response.json().get("error") == 0:
            # If successful, propagate the query to the workers
            worker_responses = []
            for worker in [WORKER_1_DNS, WORKER_2_DNS]:
                worker_response = send_query_to_server(worker, query)
                logging.info(f"worker response: {worker_response}")
                if worker_response and worker_response.status_code == 200:
                    worker_responses.append(worker_response.json().get("stdout", ""))
                else:
                    worker_responses.append(f"Error from worker {worker}: {worker_response.status_code if worker_response else 'No response'}")
            
            return QueryResponse(error=0, stdout="\n".join(worker_responses))
        else:
            # If the MANAGER fails, return its error
            return QueryResponse(error=1, stdout=manager_response.json().get("stdout", "") if manager_response else "Manager error")

    else:
        logging.error(f"unrecognized query")
        raise HTTPException(status_code=400, detail="Invalid query type")
