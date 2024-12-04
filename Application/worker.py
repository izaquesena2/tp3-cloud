from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from subprocess import Popen, PIPE
import shlex

app = FastAPI()

# Define request body schema
class QueryRequest(BaseModel):
    query: str

# Define response body schema
class QueryResponse(BaseModel):
    error: int
    stdout: str

@app.post("/run-query/", response_model=QueryResponse)
async def run_query(request: QueryRequest):
    """
    Runs a provided SQL query in a MySQL database using sudo commands.
    """
    try:
        # Step 1: Enter MySQL as root user
        mysql_command = "sudo mysql -u root"
        process1 = Popen(shlex.split(mysql_command), stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True)

        # Step 2: Use the database and execute the query
        commands = f"USE sakila;\n{request.query};\n"
        stdout, stderr = process1.communicate(input=commands)

        # Check for errors
        if process1.returncode != 0:
            return QueryResponse(error=1, stdout=stderr.strip())

        # Return the output of the query
        return QueryResponse(error=0, stdout=stdout.strip())

    except Exception as e:
        return QueryResponse(error=1, stdout=str(e))