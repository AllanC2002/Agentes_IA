import os
import json
import time
import datetime
import threading
import asyncio
import litellm
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool

import logging

# Configurar el sistema de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("app_debug.log", encoding="utf-8"), # Guarda en archivo
        logging.StreamHandler()                                 # Muestra en consola
    ]
)
logger = logging.getLogger(__name__)


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

# ─────────────────────────────────────────────
# QUEUE POR-REQUEST (no global)
# Cada llamada a /generar crea su propia queue
# y la almacena aquí con un ID único.
# ─────────────────────────────────────────────
_sesiones: dict[str, asyncio.Queue] = {}

# ─────────────────────────────────────────────
# ARCHIVOS BASE
# ─────────────────────────────────────────────
CONTEXT_BASE = """# Reglas del Sistema

## Tecnologías a usar
- Backend: FastAPI en Python
- Frontend: HTML5 + CSS en archivos separados
- Sin estilos inline, todo en style.css
- Cabe aclarar que si no es necesario backend, solo generamos HTML+CSS estático (sin endpoints ni lógica)

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

## Reglas de backend
- Solo agregar endpoints si el usuario necesita lógica real
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
# Ahora reciben la queue como parámetro de clase
# para poder emitir eventos sin depender de global
# ─────────────────────────────────────────────
def make_tools(q: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Crea instancias de herramientas vinculadas a la queue de esta sesión."""

    def emit(msg: str):
        """Envía un evento a la queue de forma thread-safe."""
        asyncio.run_coroutine_threadsafe(
            q.put({"tipo": "agente", "mensaje": msg}), loop
        )

    class LectorTool(BaseTool):
        name: str = "Lector"
        description: str = "Lee el contenido de un archivo. Úsalo para leer 'context.md', 'memory.md' o archivos generados como 'app_generada/main.py', 'app_generada/index.html', 'app_generada/style.css'"

        def _run(self, filename: str) -> str:
            try:
                clean = os.path.basename(filename)
                if not os.path.exists(clean):
                    return f"'{clean}' no existe, Asume que es un proyecto nuevo."
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
                emit("main.py guardado")
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
                emit("index.html guardado")
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
                emit("style.css guardado")
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
                emit("memory.md actualizado")
                return "OK: memory.md actualizado."
            except Exception as e:
                return f"Error: {str(e)}"

    return LectorTool(), GuardarMainPy(), GuardarIndexHtml(), GuardarStyleCss(), GuardarMemory()


# ─────────────────────────────────────────────
# CREW RUNNER
# Ahora recibe la queue y el event loop
# ─────────────────────────────────────────────
def lanzar_crew(descripcion: str, q: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Corre en un thread. Usa asyncio.run_coroutine_threadsafe para enviar eventos."""

    def emit(tipo: str, msg: str):
        asyncio.run_coroutine_threadsafe(
            q.put({"tipo": tipo, "mensaje": msg}), loop
        )

    # 1. CREAMOS EL CALLBACK PARA CAPTURAR LOS PENSAMIENTOS
    def creador_callback(nombre_agente):
        def callback(paso):
            try:
                # CrewAI devuelve una lista de acciones en el paso
                if isinstance(paso, list) and len(paso) > 0:
                    accion = paso[0][0] if isinstance(paso[0], tuple) else paso[0]
                    texto = getattr(accion, 'log', '') or getattr(accion, 'text', '')
                    if texto:
                        # Limpiamos un poco el texto y lo enviamos al frontend
                        resumen = texto.strip().split('\n')[0][:150]
                        emit("agente", f"[{nombre_agente}] {resumen}...")
            except Exception as e:
                pass # Ignoramos errores de formato del callback
        return callback

    try:
        emit("inicio", "Iniciando generación...")

        lector, guardar_main, guardar_html, guardar_css, guardar_memory = make_tools(q, loop)

        # 2. AGREGAMOS EL CALLBACK A CADA AGENTE
        planificador = Agent(
            role="Planificador",
            goal="Leer context.md y memory.md y producir un plan breve.",
            backstory="Analizas requerimientos y defines qué construir en pocas líneas.",
            llm=llm, tools=[lector], verbose=False, max_iter=3,
            step_callback=creador_callback("Planificador") 
        )
        dev_backend = Agent(
            role="Backend Developer",
            goal="Generar y guardar main.py con FastAPI.",
            backstory="Escribes código Python limpio y funcional.",
            llm=llm, tools=[guardar_main], verbose=False, max_iter=3,
            step_callback=creador_callback("Backend") 
        )
        dev_frontend = Agent(
            role="Frontend Developer",
            goal="Generar y guardar index.html.",
            backstory="Escribes HTML5 semántico y funcional.",
            llm=llm, tools=[guardar_html], verbose=False, max_iter=3,
            step_callback=creador_callback("Frontend") 
        )
        dev_css = Agent(
            role="CSS Developer",
            goal="Generar y guardar style.css.",
            backstory="Escribes CSS limpio y moderno.",
            llm=llm, tools=[guardar_css], verbose=False, max_iter=3,
            step_callback=creador_callback("CSS") 
        )
        secretario = Agent(
            role="Secretario",
            goal="Guardar exactamente 2 líneas en memory.md siguiendo la plantilla.",
            backstory="Eres una función que solo escribe 2 líneas estructuradas. Nada más.",
            llm=llm, tools=[guardar_memory], verbose=False, max_iter=2,
            step_callback=creador_callback("Secretario")
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
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
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
El usuario pidió: {descripcion}

Usa Guardar_Memory con EXACTAMENTE este texto, rellenando los corchetes:

Estado actual: [en 10 palabras qué hace la app]
Endpoints o elementos clave: [solo los endpoints o botones principales, sin mencionar archivos]

Ejemplo correcto:
Estado actual: Muestra tarjeta con stats de Cristiano Ronaldo
Endpoints o elementos clave: GET / sirve HTML estático con nombre, edad y goles

        Escribe SOLO esas 2 líneas. Nada antes, nada después.
        """,
            expected_output="2 líneas exactas con el formato Estado actual / Endpoints o elementos clave.",
            agent=secretario,
            context=[tarea_plan],
        )

        crew = Crew(
            agents=[planificador, dev_backend, dev_frontend, dev_css, secretario],
            tasks=[tarea_plan, tarea_backend, tarea_frontend, tarea_css, tarea_memoria],
            process=Process.sequential,
            verbose=True,
        )

        crew.kickoff()
        emit("finalizado", "¡App generada en app_generada/")

    except Exception as e:
        emit("error", f"Error: {str(e)}")


# ─────────────────────────────────────────────
# MODELOS
# ─────────────────────────────────────────────
class AppRequest(BaseModel):
    descripcion: str
    sesion_id: str         

class FeedbackRequest(BaseModel):
    tipo: str
    categoria: str = "General"
    descripcion: str


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.post("/generar")
async def generar(req: AppRequest):
    """
    1. Crea una asyncio.Queue para esta sesión.
    2. Lanza lanzar_crew en un thread del executor (no bloquea el event loop).
    3. Guarda la queue en _sesiones para que /progreso la consuma.
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    _sesiones[req.sesion_id] = q

    # run_in_executor: el thread pool de asyncio — no bloquea el event loop
    loop.run_in_executor(
        None,
        lanzar_crew,
        req.descripcion,
        q,
        loop,
    )
    return {"ok": True}


@app.get("/progreso/{sesion_id}")
async def progreso(sesion_id: str):
    """
    SSE por sesión. Mantiene la conexión viva enviando pings si los agentes tardan mucho.
    """
    async def stream():
        # Espera hasta 30 s a que la sesión exista
        for _ in range(30):
            if sesion_id in _sesiones:
                break
            yield 'data: {"tipo":"ping"}\n\n'
            await asyncio.sleep(1)
        else:
            yield 'data: {"tipo":"error","mensaje":"Sesión no encontrada"}\n\n'
            return

        q = _sesiones[sesion_id]
        try:
            while True:
                try:
                    # Bajamos el timeout del queue a 3 segundos. 
                    # Si no hay mensajes nuevos en 3s, lanzará TimeoutError.
                    evento = await asyncio.wait_for(q.get(), timeout=3.0)
                    data = json.dumps(evento, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    
                    if evento["tipo"] in ["finalizado", "error"]:
                        # IMPORTANTE: Pausa de medio segundo antes de romper el bucle
                        # para asegurar que Uvicorn envíe este último chunk al navegador.
                        await asyncio.sleep(0.5)
                        break
                
                except asyncio.TimeoutError:
                    # El LLM está pensando. Enviamos un ping para que 
                    # el navegador no cierre la conexión por inactividad.
                    yield 'data: {"tipo":"ping"}\n\n'
                    
        finally:
            # Limpia la sesión al terminar
            _sesiones.pop(sesion_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@app.post("/feedback")
def recibir_feedback(req: FeedbackRequest):
    try:
        historial = ""
        if os.path.exists("memory.md"):
            with open("memory.md", "r", encoding="utf-8") as f:
                historial = f.read()
                
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if req.tipo == "mejora":
            # Formato ultra-estructurado para que el Planificador lo entienda rápido
            entrada = f"\n\n## CORRECCIÓN REQUERIDA ({fecha})\n- Archivo sospechoso/Categoría: {req.categoria}\n- Instrucción: {req.descripcion}\n- Acción: Usa LectorTool para leer el código actual y aplicar esta corrección."
        else:
            entrada = f"\n\n## Feedback ({fecha})\n- App: {req.descripcion}\n"
            
        with open("memory.md", "w", encoding="utf-8") as f:
            f.write(historial + entrada)
            
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("controller:app", host="0.0.0.0", port=8000, reload=False)