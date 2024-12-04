import logging
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json

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

# Define the Proxy URL
PROXY_URL = f"http://{config.get('PROXY_DNS')}:8000/run-query"

# Define request and response schemas
class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    error: int
    stdout: str

# Helper function to send SQL queries to the Proxy
def send_query_to_proxy(query: str):
    try:
        logging.info(f"Sending request to proxy: {PROXY_URL}")
        response = requests.post(PROXY_URL, json={"query": query}, timeout=5)
        logging.info(f"Received response from proxy: {response}")
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logging.error(f"Error communicating with Proxy: {e}")
        return None

@app.post("/run-query/", response_model=QueryResponse)
async def run_query(request: QueryRequest):
    query = request.query.strip()
    logging.info(f"Forwarding query: {query} to Proxy.")
    
    # Forward query to Proxy
    response = send_query_to_proxy(query)
    if response and response.status_code == 200:
        return QueryResponse(error=0, stdout=response.json().get("stdout", ""))
    else:
        raise HTTPException(status_code=500, detail="Error processing query in Proxy")
