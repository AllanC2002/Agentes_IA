import os
import json
import time
import queue
import threading
import litellm
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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

# Cola de eventos para SSE
event_queue = queue.Queue()

# ─────────────────────────────────────────────
# HERRAMIENTAS
# ─────────────────────────────────────────────
class LectorTool(BaseTool):
    name: str = "Lector"
    description: str = "Lee un archivo. Parámetro: filename (ej: context.md)"

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
    description: str = "Guarda main.py en app_generada/. Parámetro: content."

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
    description: str = "Guarda index.html en app_generada/. Parámetro: content."

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
    description: str = "Guarda style.css en app_generada/. Parámetro: content."

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
    description: str = "Actualiza memory.md en la raíz. Parámetro: content."

    def _run(self, content: str) -> str:
        try:
            with open("memory.md", "w", encoding="utf-8") as f:
                f.write(content)
            event_queue.put({"tipo": "agente", "mensaje": "✅ memory.md actualizado"})
            return "OK: memory.md actualizado."
        except Exception as e:
            return f"Error: {str(e)}"

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
# CREW RUNNER
# ─────────────────────────────────────────────
def lanzar_crew(descripcion: str):
    try:
        event_queue.put({"tipo": "inicio", "mensaje": "🚀 Iniciando generación..."})

        with open("context.md", "w") as f:
            f.write(f"""# Proyecto
El usuario quiere: {descripcion}

Reglas técnicas:
- Backend: FastAPI en Python
- Frontend: HTML5 + CSS en archivos separados
- GET / sirve index.html
- CSS linkado como href="/static/style.css"
- El HTML debe tener fetch() a los endpoints de la API
- CSS dark mode
""")

        if not os.path.exists("memory.md"):
            with open("memory.md", "w") as f:
                f.write("# Memoria\nIteración 0: Sin ejecuciones previas.\n")

        # Agentes
        event_queue.put({"tipo": "agente", "mensaje": "🧠 Planificador analizando..."})
        planificador = Agent(
            role="Planificador",
            goal="Leer context.md y memory.md y producir un plan breve.",
            backstory="Lees archivos y defines qué construir en pocas líneas.",
            llm=llm, tools=[LectorTool()], verbose=False, max_iter=3,
        )

        event_queue.put({"tipo": "agente", "mensaje": "⚙️ Backend Developer listo..."})
        dev_backend = Agent(
            role="Backend Developer",
            goal="Generar y guardar main.py con FastAPI.",
            backstory="Escribes solo el código Python necesario y lo guardas.",
            llm=llm, tools=[GuardarMainPy()], verbose=False, max_iter=3,
        )

        event_queue.put({"tipo": "agente", "mensaje": "🎨 Frontend Developer listo..."})
        dev_frontend = Agent(
            role="Frontend Developer",
            goal="Generar y guardar index.html.",
            backstory="Escribes HTML5 funcional y lo guardas.",
            llm=llm, tools=[GuardarIndexHtml()], verbose=False, max_iter=3,
        )

        dev_css = Agent(
            role="CSS Developer",
            goal="Generar y guardar style.css con dark mode.",
            backstory="Escribes CSS limpio y lo guardas.",
            llm=llm, tools=[GuardarStyleCss()], verbose=False, max_iter=3,
        )

        secretario = Agent(
            role="Secretario",
            goal="Actualizar memory.md con resumen breve.",
            backstory="Documentas en pocas líneas lo que se construyó.",
            llm=llm, tools=[GuardarMemory()], verbose=False, max_iter=3,
        )

        # Tareas
        tarea_plan = Task(
    description=f"""
Lee 'context.md' y 'memory.md' con Lector.
El usuario quiere: {descripcion}

Analiza si la app REALMENTE necesita un backend con FastAPI o si puede ser solo HTML + CSS.
- Si solo muestra contenido estático (imágenes, texto, listas) → NO necesita backend, solo HTML y CSS
- Si necesita guardar datos, consultar una API externa, o procesar algo → SÍ necesita backend

Produce un plan técnico breve (máximo 8 líneas) que incluya:
- ¿Necesita backend? Sí o No
- Qué debe mostrar el HTML
- Qué estilos CSS aplicar
""",
    expected_output="Plan técnico en 8 líneas con decisión clara sobre si necesita backend o no.",
    agent=planificador,
        )

        tarea_backend = Task(
    description="""
Lee el plan del contexto anterior.
Si el plan dice que NO necesita backend, usa Guardar_MainPy para guardar este código mínimo exacto:

from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()

@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

Si el plan dice que SÍ necesita backend, genera main.py con los endpoints necesarios usando EXACTAMENTE estos imports:

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()

@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

# endpoints adicionales aquí

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
""",
    expected_output="Confirmación de que main.py fue guardado.",
    agent=dev_backend,
    context=[tarea_plan],
        )

        tarea_frontend = Task(
            description="""
Basándote en el plan, usa Guardar_IndexHtml para guardar HTML5 con:
- <link rel="stylesheet" href="/static/style.css">
- Los elementos que definió el planificador
- fetch() a los endpoints de la API
Menos de 40 líneas.
""",
            expected_output="Confirmación de que index.html fue guardado.",
            agent=dev_frontend,
            context=[tarea_plan],
        )

        tarea_css = Task(
            description="""
Basándote en el plan, usa Guardar_StyleCss para guardar CSS con:
- body: fondo #1a1a2e, color blanco, fuente sans-serif, centrado
- button: fondo #6c63ff, sin borde, padding 10px 20px, cursor pointer
- button:hover: fondo #574fd6
Menos de 30 líneas.
""",
            expected_output="Confirmación de que style.css fue guardado.",
            agent=dev_css,
            context=[tarea_plan],
        )

        tarea_memoria = Task(
            description="Usa Guardar_Memory para actualizar memory.md con resumen breve de esta iteración. Máximo 10 líneas.",
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
        event_queue.put({"tipo": "finalizado", "mensaje": "🎉 ¡App generada exitosamente en app_generada/"})

    except Exception as e:
        event_queue.put({"tipo": "error", "mensaje": f"❌ Error: {str(e)}"})

# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────
class AppRequest(BaseModel):
    descripcion: str

@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.post("/generar")
def generar(req: AppRequest):
    # Lanza el crew en un thread separado para no bloquear
    thread = threading.Thread(target=lanzar_crew, args=(req.descripcion,))
    thread.daemon = True
    thread.start()
    return {"ok": True}

@app.get("/progreso")
def progreso():
    def stream():
        while True:
            try:
                evento = event_queue.get(timeout=60)
                data = json.dumps(evento, ensure_ascii=False)
                yield f"data: {data}\n\n"
                if evento["tipo"] in ["finalizado", "error"]:
                    break
            except queue.Empty:
                yield "data: {\"tipo\": \"ping\"}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("controller:app", host="0.0.0.0", port=8000, reload=False)