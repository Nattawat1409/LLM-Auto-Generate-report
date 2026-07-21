from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field 
from typing import List, Optional
from app.models import state
from typing_extensions import Literal 
from app.graph import graph # make /app as package to import 

app = FastAPI(title="LLM auto-generate workflow service")

user_action1 = ["approve","requery"] 

class Queryrequest(BaseModel):
    user_message: str = Field(description="getting user message to fetching data")
    user_decesion: str = Field(description="user can choose between approve or requerty")
    thread_id: Optional[str] = Field(default="default_thread", description="ID for memorize context within conversation")
    
class Queryresponse(BaseModel):
    text2SQL : str = Field(description="after converting the uesr query to SQL data from database information")
    check_correctness: str = Field(description="Show the data correctness to user to validate data")




@app.post("/run-workflow", response_model=WorkflowResponse)
async def run_workflow(payload: WorkflowRequest):
    try:
        # Prepare the initial state dict required by LangGraph
        initial_state = {"input_text": payload.message}
        
        # Execute the graph synchronously or asynchronously (.ainvoke)
        final_state = await graph.invoke(initial_state)
        
        # Extract and return the final state payload
        output = final_state.get("processed_text", "No response generated")
        return payload(result=output)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    



# root path
@app.get("/")
async def read_root():
    return {"message":"Server is running..."}

# Start session stop at HITL
@app.post("/reports",response_model=Queryresponse)
async def prepare_report(request : Queryrequest):
    user_input = {"user_input": request.user_message} # get user massage 

    try:
        is_relate = await graph.invoke(user_input) # get the result of read schema 
        send_to_schema = is_relate.get("is_question_relate")
        response = graph.invoke(send_to_schema)
        return request(result=response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    

# approvement at step HITL
@app.post("/reports/{id}/review")
async def read_root(request : Queryrequest):
    return 

# get conversation from user 
@app.get("/conversation")
async def show_item(input: str, llm_result:str |None =None):
    return {"input":input , "llm_result":llm_result}

@app.get("/linked")
async def read_root():
    return {"Hello": "World"}

@app.post("/testPost")
async def get_input():
    return {"user_input":"sucessfully!"}
