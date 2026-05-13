from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/api/saludo")
def saludo():
    return {"mensaje": "Hola desde la API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)