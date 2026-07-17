from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}
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