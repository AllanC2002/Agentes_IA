import os
import json
import time
import queue
import datetime
import threading
import litellm
import asyncio
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool

load_dotenv()

litellm.num_retries = 5
litellm.retry_after = 15

original_completion = litellm.completion
def completion_con_pausa(*args, **kwargs):
    time.sleep(8)
    return original_completion(*args, **kwargs)
litellm.completion = completion_con_pausa

# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

event_queue = queue.Queue()

# ─────────────────────────────────────────────
# ARCHIVOS BASE (se crean una sola vez)
# ─────────────────────────────────────────────
CONTEXT_BASE = """# Reglas del Sistema

## Tecnologías obligatorias
- Backend: FastAPI en Python
- Frontend: HTML5 + CSS en archivos separados
- Sin estilos inline, todo en style.css

## Imports obligatorios en main.py
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

## Reglas de HTML
- Siempre: <link rel="stylesheet" href="/static/style.css">
- fetch() debe apuntar a endpoints reales definidos en el plan
- Sin librerías externas salvo Google Fonts

## Reglas de imágenes
- Nunca uses picsum.photos (imágenes aleatorias sin contexto)
- Para perros: https://placedog.net/500/300
- Para gatos: https://cataas.com/cat
- Para otros temas: https://source.unsplash.com/500x300/?[tema_en_ingles]

## Reglas de backend
- Solo agregar endpoints si el usuario necesita lógica real
- Si es solo contenido estático, main.py solo sirve el index.html
- CSS dark mode siempre
"""

if not os.path.exists("context.md"):
    with open("context.md", "w", encoding="utf-8") as f:
        f.write(CONTEXT_BASE)

if not os.path.exists("memory.md"):
    with open("memory.md", "w", encoding="utf-8") as f:
        f.write("# Memoria del Sistema\nIteración 0: Sin ejecuciones previas.\n")

# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────
llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    api_key=os.environ.get("GROQ_API_KEY"),
    temperature=0,
    max_retries=5,
    timeout=60,
)

# ─────────────────────────────────────────────
# HERRAMIENTAS
# ─────────────────────────────────────────────
class LectorTool(BaseTool):
    name: str = "Lector"
    description: str = "Lee un archivo local. Parámetro: filename (ej: context.md)"

    def _run(self, filename: str) -> str:
        try:
            clean = os.path.basename(filename)
            if not os.path.exists(clean):
                return f"'{clean}' no existe, continúa sin él."
            with open(clean, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error: {str(e)}"

class GuardarMainPy(BaseTool):
    name: str = "Guardar_MainPy"
    description: str = "Guarda main.py en app_generada/. Parámetro: content (código Python)."

    def _run(self, content: str) -> str:
        try:
            os.makedirs("app_generada", exist_ok=True)
            with open("app_generada/main.py", "w", encoding="utf-8") as f:
                f.write(content)
            event_queue.put({"tipo": "agente", "mensaje": "✅ main.py guardado"})
            return "OK: main.py guardado."
        except Exception as e:
            return f"Error: {str(e)}"

class GuardarIndexHtml(BaseTool):
    name: str = "Guardar_IndexHtml"
    description: str = "Guarda index.html en app_generada/. Parámetro: content (HTML)."

    def _run(self, content: str) -> str:
        try:
            os.makedirs("app_generada", exist_ok=True)
            with open("app_generada/index.html", "w", encoding="utf-8") as f:
                f.write(content)
            event_queue.put({"tipo": "agente", "mensaje": "✅ index.html guardado"})
            return "OK: index.html guardado."
        except Exception as e:
            return f"Error: {str(e)}"

class GuardarStyleCss(BaseTool):
    name: str = "Guardar_StyleCss"
    description: str = "Guarda style.css en app_generada/. Parámetro: content (CSS)."

    def _run(self, content: str) -> str:
        try:
            os.makedirs("app_generada", exist_ok=True)
            with open("app_generada/style.css", "w", encoding="utf-8") as f:
                f.write(content)
            event_queue.put({"tipo": "agente", "mensaje": "✅ style.css guardado"})
            return "OK: style.css guardado."
        except Exception as e:
            return f"Error: {str(e)}"

class GuardarMemory(BaseTool):
    name: str = "Guardar_Memory"
    description: str = "Agrega una entrada al memory.md sin borrar el historial. Parámetro: content."

    def _run(self, content: str) -> str:
        try:
            historial = ""
            if os.path.exists("memory.md"):
                with open("memory.md", "r", encoding="utf-8") as f:
                    historial = f.read()
            fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            nueva_entrada = f"\n\n## Iteración {fecha}\n{content}"
            with open("memory.md", "w", encoding="utf-8") as f:
                f.write(historial + nueva_entrada)
            event_queue.put({"tipo": "agente", "mensaje": "✅ memory.md actualizado"})
            return "OK: memory.md actualizado."
        except Exception as e:
            return f"Error: {str(e)}"

# ─────────────────────────────────────────────
# CREW RUNNER
# ─────────────────────────────────────────────
def lanzar_crew(descripcion: str):
    try:
        event_queue.put({"tipo": "inicio", "mensaje": "🚀 Iniciando generación..."})

        planificador = Agent(
            role="Planificador",
            goal="Leer context.md y memory.md y producir un plan breve.",
            backstory="Analizas requerimientos y defines qué construir en pocas líneas.",
            llm=llm, tools=[LectorTool()], verbose=False, max_iter=3,
        )
        dev_backend = Agent(
            role="Backend Developer",
            goal="Generar y guardar main.py con FastAPI.",
            backstory="Escribes código Python limpio y funcional.",
            llm=llm, tools=[GuardarMainPy()], verbose=False, max_iter=3,
        )
        dev_frontend = Agent(
            role="Frontend Developer",
            goal="Generar y guardar index.html.",
            backstory="Escribes HTML5 semántico y funcional.",
            llm=llm, tools=[GuardarIndexHtml()], verbose=False, max_iter=3,
        )
        dev_css = Agent(
            role="CSS Developer",
            goal="Generar y guardar style.css.",
            backstory="Escribes CSS limpio y moderno.",
            llm=llm, tools=[GuardarStyleCss()], verbose=False, max_iter=3,
        )
        secretario = Agent(
            role="Secretario",
            goal="Actualizar memory.md con aprendizajes de esta iteración.",
            backstory="Documentas qué se hizo, qué funcionó y qué mejorar.",
            llm=llm, tools=[GuardarMemory()], verbose=False, max_iter=3,
        )

        tarea_plan = Task(
            description=f"""
Lee 'context.md' y 'memory.md' con Lector.
El usuario quiere: {descripcion}

Decide si necesita backend (lógica/datos) o solo HTML+CSS (contenido estático).
Produce un plan de máximo 8 líneas con:
- ¿Necesita backend? Sí/No
- Qué mostrar en el HTML
- Qué endpoints si aplica
- Qué estilos CSS
""",
            expected_output="Plan técnico en 8 líneas.",
            agent=planificador,
        )

        tarea_backend = Task(
            description="""
Según el plan:
- Si NO necesita backend: guarda main.py mínimo que solo sirve index.html
- Si SÍ necesita backend: genera main.py con los endpoints del plan

Usa SIEMPRE estos imports exactos:
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
""",
            expected_output="Confirmación de que main.py fue guardado.",
            agent=dev_backend,
            context=[tarea_plan],
        )

        tarea_frontend = Task(
            description="""
Según el plan, guarda index.html con:
- <link rel="stylesheet" href="/static/style.css">
- El contenido que definió el planificador
- Si hay endpoints: fetch() a esos endpoints
- Si hay imágenes: usa URLs reales según las reglas del context.md
- Menos de 40 líneas
""",
            expected_output="Confirmación de que index.html fue guardado.",
            agent=dev_frontend,
            context=[tarea_plan],
        )

        tarea_css = Task(
            description="""
Según el plan, guarda style.css con:
- body: fondo #1a1a2e, color blanco, sans-serif, centrado
- button: fondo #6c63ff, sin borde, padding 10px 20px, cursor pointer
- button:hover: fondo #574fd6
- Menos de 30 líneas
""",
            expected_output="Confirmación de que style.css fue guardado.",
            agent=dev_css,
            context=[tarea_plan],
        )

        tarea_memoria = Task(
            description=f"""
Usa Guardar_Memory para agregar al historial:
- Usuario pidió: {descripcion}
- Archivos generados
- Endpoints creados si aplica
- Recursos externos usados (URLs de imágenes, APIs)
- Qué se podría mejorar
Máximo 10 líneas.
""",
            expected_output="Confirmación de que memory.md fue actualizado.",
            agent=secretario,
            context=[tarea_backend, tarea_frontend, tarea_css],
        )

        crew = Crew(
            agents=[planificador, dev_backend, dev_frontend, dev_css, secretario],
            tasks=[tarea_plan, tarea_backend, tarea_frontend, tarea_css, tarea_memoria],
            process=Process.sequential,
            verbose=False,
        )

        crew.kickoff()
        event_queue.put({"tipo": "finalizado", "mensaje": "🎉 ¡App generada en app_generada/"})

    except Exception as e:
        event_queue.put({"tipo": "error", "mensaje": f"❌ Error: {str(e)}"})

# ─────────────────────────────────────────────
# MODELOS
# ─────────────────────────────────────────────
class AppRequest(BaseModel):
    descripcion: str

class FeedbackRequest(BaseModel):
    tipo: str
    descripcion: str

# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.post("/generar")
def generar(req: AppRequest):
    thread = threading.Thread(target=lanzar_crew, args=(req.descripcion,))
    thread.daemon = True
    thread.start()
    return {"ok": True}

@app.get("/progreso")
async def progreso():
    async def stream():
        finalizado = False
        while not finalizado:
            try:
                evento = event_queue.get_nowait()
                data = json.dumps(evento, ensure_ascii=False)
                yield f"data: {data}\n\n"
                if evento["tipo"] in ["finalizado", "error"]:
                    finalizado = True
            except queue.Empty:
                yield 'data: {"tipo": "ping"}\n\n'
                await asyncio.sleep(1)
    
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

@app.post("/feedback")
def recibir_feedback(req: FeedbackRequest):
    try:
        historial = ""
        if os.path.exists("memory.md"):
            with open("memory.md", "r", encoding="utf-8") as f:
                historial = f.read()
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        entrada = f"\n\n## Feedback {fecha}\n- App: {req.descripcion}\n- Resultado: 👍 Aprobada"
        with open("memory.md", "w", encoding="utf-8") as f:
            f.write(historial + entrada)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("controller:app", host="0.0.0.0", port=8000, reload=False)