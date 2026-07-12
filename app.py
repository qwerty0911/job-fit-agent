from fastapi import FastAPI
from llm import get_llm
from schema import *
from graph import graph

app = FastAPI()


@app.post("/chat")
async def chat(request: ChatRequest):

    result = await graph.ainvoke({
        "message": request.message
    })

    return {"response": result["response"]}