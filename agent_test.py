import os
import litellm
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool
import time

load_dotenv()

litellm.num_retries = 5
litellm.retry_after = 15

original_completion = litellm.completion

def completion_con_pausa(*args, **kwargs):
    time.sleep(8)  # 8 segundos entre cada llamada al LLM
    return original_completion(*args, **kwargs)

litellm.completion = completion_con_pausa

# ─────────────────────────────────────────────
# HERRAMIENTAS — guardado separado por archivo
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

# Una herramienta por archivo — sin parámetro 'content', lo lee del output anterior
class GuardarMainPy(BaseTool):
    name: str = "Guardar_MainPy"
    description: str = "Guarda el contenido dado en app_generada/main.py. Parámetro: content (código Python completo)."

    def _run(self, content: str) -> str:
        try:
            os.makedirs("app_generada", exist_ok=True)
            with open("app_generada/main.py", "w", encoding="utf-8") as f:
                f.write(content)
            return "OK: main.py guardado."
        except Exception as e:
            return f"Error: {str(e)}"

class GuardarIndexHtml(BaseTool):
    name: str = "Guardar_IndexHtml"
    description: str = "Guarda el contenido dado en app_generada/index.html. Parámetro: content (HTML completo)."

    def _run(self, content: str) -> str:
        try:
            os.makedirs("app_generada", exist_ok=True)
            with open("app_generada/index.html", "w", encoding="utf-8") as f:
                f.write(content)
            return "OK: index.html guardado."
        except Exception as e:
            return f"Error: {str(e)}"

class GuardarStyleCss(BaseTool):
    name: str = "Guardar_StyleCss"
    description: str = "Guarda el contenido dado en app_generada/style.css. Parámetro: content (CSS completo)."

    def _run(self, content: str) -> str:
        try:
            os.makedirs("app_generada", exist_ok=True)
            with open("app_generada/style.css", "w", encoding="utf-8") as f:
                f.write(content)
            return "OK: style.css guardado."
        except Exception as e:
            return f"Error: {str(e)}"

class GuardarMemory(BaseTool):
    name: str = "Guardar_Memory"
    description: str = "Actualiza memory.md en la raíz. Parámetro: content (texto del resumen)."

    def _run(self, content: str) -> str:
        try:
            with open("memory.md", "w", encoding="utf-8") as f:
                f.write(content)
            return "OK: memory.md actualizado."
        except Exception as e:
            return f"Error: {str(e)}"

# ─────────────────────────────────────────────
# ARCHIVOS INICIALES
# ─────────────────────────────────────────────
if not os.path.exists("context.md"):
    with open("context.md", "w") as f:
        f.write("""# Proyecto
FastAPI app con:
- GET / sirve index.html
- GET /api/saludo retorna {"mensaje": "Hola"}
- HTML con botón que hace fetch a /api/saludo y muestra respuesta
- CSS dark mode simple
""")

if not os.path.exists("memory.md"):
    with open("memory.md", "w") as f:
        f.write("# Memoria\nIteración 0: Sin ejecuciones previas.\n")

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
"""
llm = LLM(
    model="gemini/gemini-2.0-flash",
    api_key=os.environ.get("GOOGLE_API_KEY"),
    temperature=0,
    max_retries=5,
    timeout=60,
)
"""



# ─────────────────────────────────────────────
# AGENTES — uno por archivo para minimizar tokens
# ─────────────────────────────────────────────
planificador = Agent(
    role="Planificador",
    goal="Leer context.md y memory.md y producir un plan breve.",
    backstory="Lees archivos y defines qué construir en pocas líneas.",
    llm=llm,
    tools=[LectorTool()],
    verbose=True,
    max_iter=3,
)

dev_backend = Agent(
    role="Backend Developer",
    goal="Generar y guardar main.py con FastAPI.",
    backstory="Escribes solo el código Python necesario y lo guardas.",
    llm=llm,
    tools=[GuardarMainPy()],
    verbose=True,
    max_iter=3,
)

dev_frontend = Agent(
    role="Frontend Developer",
    goal="Generar y guardar index.html.",
    backstory="Escribes HTML5 funcional y lo guardas.",
    llm=llm,
    tools=[GuardarIndexHtml()],
    verbose=True,
    max_iter=3,
)

dev_css = Agent(
    role="CSS Developer",
    goal="Generar y guardar style.css con dark mode.",
    backstory="Escribes CSS limpio y lo guardas.",
    llm=llm,
    tools=[GuardarStyleCss()],
    verbose=True,
    max_iter=3,
)

secretario = Agent(
    role="Secretario",
    goal="Actualizar memory.md con resumen breve de esta iteración.",
    backstory="Documentas en pocas líneas lo que se construyó.",
    llm=llm,
    tools=[GuardarMemory()],
    verbose=True,
    max_iter=3,
)

# ─────────────────────────────────────────────
# TAREAS — expected_output corto = menos tokens
# ─────────────────────────────────────────────
tarea_plan = Task(
    description="Lee 'context.md' y 'memory.md' con Lector. Produce un plan de máximo 8 líneas.",
    expected_output="Plan técnico en 8 líneas o menos.",
    agent=planificador,
)

tarea_backend = Task(
    description="""
Usa Guardar_MainPy para guardar este código exacto, sin modificarlo:

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

Llama a Guardar_MainPy con ese contenido como 'content'.
""",
    expected_output="Confirmación de que main.py fue guardado.",
    agent=dev_backend,
    context=[tarea_plan],
)

tarea_frontend = Task(
    description="""
Usa Guardar_IndexHtml para guardar un HTML5 que tenga:
- <link rel="stylesheet" href="style.css">
- Un <h1> con el título "Mi App"
- Un <button id="btn">Obtener Saludo</button>
- Un <div id="resultado"></div>
- Un <script> que haga:
    document.getElementById('btn').addEventListener('click', () => {
        fetch('/api/saludo')
            .then(r => r.json())
            .then(data => document.getElementById('resultado').innerText = data.mensaje)
    })
Menos de 35 líneas.
""",
    expected_output="Confirmación de que index.html fue guardado.",
    agent=dev_frontend,
    context=[tarea_plan],
)

tarea_css = Task(
    description="""
Usa Guardar_StyleCss para guardar CSS con:
- body: fondo #1a1a2e, color blanco, fuente sans-serif, centrado
- button: fondo #6c63ff, sin borde, padding 10px 20px, cursor pointer
- button:hover: fondo #574fd6
Menos de 25 líneas.
""",
    expected_output="Confirmación de que style.css fue guardado.",
    agent=dev_css,
    context=[tarea_plan],
)

tarea_memoria = Task(
    description="Usa Guardar_Memory para guardar en memory.md: historial previo + 'Iteración actual: se generaron main.py, index.html, style.css'. Máximo 10 líneas totales.",
    expected_output="Confirmación de que memory.md fue actualizado.",
    agent=secretario,
    context=[tarea_backend, tarea_frontend, tarea_css],
)

# ─────────────────────────────────────────────
# CREW
# ─────────────────────────────────────────────
crew = Crew(
    agents=[planificador, dev_backend, dev_frontend, dev_css, secretario],
    tasks=[tarea_plan, tarea_backend, tarea_frontend, tarea_css, tarea_memoria],
    process=Process.sequential,
    verbose=True,
)

result = crew.kickoff()
print("\n✅ Listo. Archivos en 'app_generada/'")
print("▶️  Ejecutar: cd app_generada && uvicorn main:app --reload")