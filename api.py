from fastapi import *
from fastapi.responses import HTMLResponse,StreamingResponse
from fastapi.sse import EventSourceResponse
import uvicorn,inference,json
app=FastAPI()
manual=inference.readManual()

@app.options("/ping")
async def ping():
    return "success"

@app.post("/agent",response_class=EventSourceResponse)
async def agent(prompt=Form()):
    prompt=f"{inference.cls}system\n{manual}\n Use any tools if necessary.\nuser\n{prompt}\nassistant\n<think>\n\n</think>\n\n"
    tokenCounter = 0
    for token in inference.generate_response(inference.model, inference.tokenizer, prompt, 10000, top_k=100,temp=1.0):
        tokenCounter += 1
        yield json.dumps({"token": tokenCounter, "string": token})



uvicorn.run(app, host="0.0.0.0", port=8000)