import os
import json
import time
import datetime
import threading
import asyncio
import litellm
import logging
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("app_debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

litellm.num_retries = 5 # Litellm pertence a crewAI y enruta las peticiones al LLM. Limitar a 5 reintentos para evitar loops infinitos
litellm.retry_after = 15 # Tiempo de espera entre reintentos, en segundos. Para dar mas tiempo al LLM a recuperarse y evitar bloqueos temporales.

original_completion = litellm.completion # litellm.completion es la funcion que hace las llamadas al LLM. La vamos a envolver para agregarle una pausa de 12 segundos antes de cada llamada

def completion_con_pausa(*args, **kwargs):
    time.sleep(12)
    return original_completion(*args, **kwargs)

litellm.completion = completion_con_pausa

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar el directorio actual como /static para que los agentes puedan guardar los archivos generados y el frontend pueda acceder a ellos
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) #Ruta actual absoluta sin el archivo final, para usarlo como base de los archivos estáticos
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static") # Enruta para que las solicitudes a /static/ se sirvan desde el directorio BASE_DIR, donde los agentes guardarán los archivos generados

_sesiones: dict[str, asyncio.Queue] = {} #Clarificar

CONTEXT_BASE = """# Reglas del Sistema

## Tecnologías a usar
- Backend: FastAPI en Python
- Frontend: HTML5 + CSS en archivos separados
- Sin estilos inline, todo en style.css
- Si no es necesario backend, solo generamos HTML+CSS estático (sin endpoints ni lógica)

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

llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    api_key=os.environ.get("GROQ_API_KEY"),
    temperature=0,
    max_retries=5,
    timeout=60,
)

#pendiente
def make_tools(q: asyncio.Queue, loop: asyncio.AbstractEventLoop): 

    def emit(msg: str):
        asyncio.run_coroutine_threadsafe(
            q.put({"tipo": "agente", "mensaje": msg}), loop
        )

    class LectorTool(BaseTool):
        name: str = "Lector"
        description: str = "Lee el contenido de un archivo. Usalo para leer 'context.md', 'memory.md' o archivos generados como 'app_generada/main.py', 'app_generada/index.html', 'app_generada/style.css'"

        def _run(self, filename: str) -> str:
            try:
                clean = os.path.basename(filename)
                if not os.path.exists(clean):
                    return f"'{clean}' no existe. Asume que es un proyecto nuevo."
                with open(clean, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error: {str(e)}"

    class GuardarMainPy(BaseTool):
        name: str = "Guardar_MainPy"
        description: str = "Guarda main.py en app_generada/. Parametro: content (codigo Python completo)."

        def _run(self, content: str) -> str:
            try:
                os.makedirs("app_generada", exist_ok=True)
                with open("app_generada/main.py", "w", encoding="utf-8") as f:
                    f.write(content)
                emit("main.py guardado")
                return "OK: main.py guardado en app_generada/main.py."
            except Exception as e:
                return f"Error: {str(e)}"

    class GuardarIndexHtml(BaseTool):
        name: str = "Guardar_IndexHtml"
        description: str = "Guarda index.html en app_generada/. Parametro: content (HTML completo)."

        def _run(self, content: str) -> str:
            try:
                os.makedirs("app_generada", exist_ok=True)
                with open("app_generada/index.html", "w", encoding="utf-8") as f:
                    f.write(content)
                emit("index.html guardado")
                return "OK: index.html guardado en app_generada/index.html."
            except Exception as e:
                return f"Error: {str(e)}"

    class GuardarStyleCss(BaseTool):
        name: str = "Guardar_StyleCss"
        description: str = "Guarda style.css en app_generada/. Parametro: content (CSS completo)."

        def _run(self, content: str) -> str:
            try:
                os.makedirs("app_generada", exist_ok=True)
                with open("app_generada/style.css", "w", encoding="utf-8") as f:
                    f.write(content)
                emit("style.css guardado")
                return "OK: style.css guardado en app_generada/style.css."
            except Exception as e:
                return f"Error: {str(e)}"

    class GuardarMemory(BaseTool):
        name: str = "Guardar_Memory"
        description: str = "Agrega una entrada al memory.md sin borrar el historial. Parametro: content."

        def _run(self, content: str) -> str:
            try:
                historial = ""
                if os.path.exists("memory.md"):
                    with open("memory.md", "r", encoding="utf-8") as f:
                        historial = f.read()
                fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                nueva_entrada = f"\n\n## Iteracion {fecha}\n{content}"
                with open("memory.md", "w", encoding="utf-8") as f:
                    f.write(historial + nueva_entrada)
                emit("memory.md actualizado")
                return "OK: memory.md actualizado."
            except Exception as e:
                return f"Error: {str(e)}"

    return LectorTool(), GuardarMainPy(), GuardarIndexHtml(), GuardarStyleCss(), GuardarMemory()


def lanzar_crew(descripcion: str, q: asyncio.Queue, loop: asyncio.AbstractEventLoop):

    def emit(tipo: str, msg: str):
        asyncio.run_coroutine_threadsafe(
            q.put({"tipo": tipo, "mensaje": msg}), loop
        )

    def creador_callback(nombre_agente):
        #pendiente
        def callback(paso):
            try:
                if isinstance(paso, list) and len(paso) > 0:
                    accion = paso[0][0] if isinstance(paso[0], tuple) else paso[0]
                    texto = getattr(accion, 'log', '') or getattr(accion, 'text', '')
                    if texto:
                        resumen = texto.strip().split('\n')[0][:150]
                        emit("agente", f"[{nombre_agente}] {resumen}...")
            except Exception:
                pass
        return callback

    try:
        emit("inicio", "Iniciando generacion...")

        lector, guardar_main, guardar_html, guardar_css, guardar_memory = make_tools(q, loop)

        planificador = Agent(
            role="Planificador Tecnico",
            goal=(
                "Leer context.md y memory.md completos antes de cualquier decision. "
                "Producir un plan tecnico preciso que los demas agentes puedan seguir sin ambiguedad."
            ),
            backstory=(
                "Eres el arquitecto del proyecto. Tu primera accion SIEMPRE es leer context.md y memory.md "
                "usando la herramienta Lector, para conocer las reglas y el historial de errores anteriores. "
                "Con base en eso defines si se necesita backend o no, que debe mostrar el HTML y que estilos aplicar. "
                "Nunca inventas rutas ni estructuras: todo lo que defines viene de las reglas del context.md."
            ),
            llm=llm,
            tools=[lector],
            verbose=False,
            max_iter=4,
            step_callback=creador_callback("Planificador"),
        )

        dev_backend = Agent(
            role="Backend Developer Python/FastAPI",
            goal=(
                "Generar main.py correcto y guardarlo usando Guardar_MainPy. "
                "El archivo debe funcionar sin modificaciones adicionales."
            ),
            backstory=(
                "Eres un experto en FastAPI. Conoces de memoria la estructura obligatoria: "
                "BASE_DIR = os.path.dirname(os.path.abspath(__file__)), "
                "app.mount('/static', StaticFiles(directory=BASE_DIR), name='static'), "
                "endpoint raiz que devuelve FileResponse(os.path.join(BASE_DIR, 'index.html')), "
                "y uvicorn.run('main:app', host='0.0.0.0', port=8001, reload=True) en el bloque __main__. "
                "Si el plan dice que NO necesita backend, igual generas el main.py minimo con solo el endpoint raiz. "
                "Nunca omites los imports obligatorios ni cambias los nombres de los archivos."
            ),
            llm=llm,
            tools=[guardar_main],
            verbose=False,
            max_iter=3,
            step_callback=creador_callback("Backend"),
        )

        dev_frontend = Agent(
            role="Frontend Developer HTML5",
            goal=(
                "Generar index.html correcto y guardarlo usando Guardar_IndexHtml. "
                "El HTML debe ser funcional, semantico y seguir TODAS las reglas del plan."
            ),
            backstory=(
                "Eres especialista en HTML5 semantico. Tienes UNA regla que jamas rompes: "
                "el enlace al CSS SIEMPRE es exactamente: <link rel='stylesheet' href='/static/style.css'> "
                "La barra inicial y la carpeta /static/ son OBLIGATORIAS. "
                "PROHIBIDO escribir: href='style.css' | href='css/style.css' | href='./style.css'. "
                "La ruta UNICA y CORRECTA es: /static/style.css — sin excepciones. "
                "Si el plan define endpoints de API, usas fetch() con URL absoluta al puerto 8001. "
                "Si el plan dice que es estatico, pones los datos directamente en el HTML sin fetch(). "
                "El body SIEMPRE comienza con un <h1> con el titulo descriptivo del tema de la app."
            ),
            llm=llm,
            tools=[guardar_html],
            verbose=False,
            max_iter=3,
            step_callback=creador_callback("Frontend"),
        )

        dev_css = Agent(
            role="CSS Developer",
            goal=(
                "Generar style.css correcto y guardarlo usando Guardar_StyleCss. "
                "El CSS debe implementar dark mode y seguir los estilos del plan."
            ),
            backstory=(
                "Eres experto en CSS3. Siempre usas dark mode como base: fondo #1a1a2e, texto blanco. "
                "Tu archivo se llama exactamente style.css y el HTML lo carga desde /static/style.css. "
                "Nunca usas estilos inline en el HTML — todo va en este archivo. "
                "Mantienes el CSS limpio, sin redundancias y en menos de 60 lineas salvo que el plan exija mas."
            ),
            llm=llm,
            tools=[guardar_css],
            verbose=False,
            max_iter=3,
            step_callback=creador_callback("CSS"),
        )

        secretario = Agent(
            role="Secretario de Memoria",
            goal="Llamar a Guardar_Memory una sola vez con exactamente 2 lineas. Sin texto adicional.",
            backstory=(
                "Eres una funcion de escritura, no un redactor creativo. "
                "Tu unica tarea es llamar a Guardar_Memory con exactamente 2 lineas siguiendo la plantilla. "
                "No escribes 'que se podria mejorar', no elaboras. Solo las 2 lineas de la plantilla"
            ),
            llm=llm,
            tools=[guardar_memory],
            verbose=False,
            max_iter=2,
            step_callback=creador_callback("Secretario"),
        )

        # ─────────────────────────────────────────────
        # TAREAS
        # ─────────────────────────────────────────────
        tarea_plan = Task(
            description=f"""
PASO 1: Usa Lector para leer 'context.md'. Lee el contenido completo.
PASO 2: Usa Lector para leer 'memory.md'. Lee el contenido completo, especialmente las secciones CORRECCION REQUERIDA y Feedback.
PASO 3: Con base en ambos archivos y el requerimiento del usuario, produce el plan.

Requerimiento del usuario: {descripcion}

El plan debe responder exactamente estas 5 preguntas en orden:
1. Backend: Si/No — Solo Si si hay logica dinamica (calculos, datos en tiempo real, BD)
2. Contenido HTML: lista de elementos concretos a mostrar
3. Endpoints: rutas exactas /api/... con su metodo HTTP, o "No aplica"
4. Estilos CSS: colores, fuentes, layout especifico
5. Correcciones de memory.md: lista las pendientes o escribe "Sin correcciones pendientes"
""",
            expected_output=(
                "Plan tecnico numerado en exactamente 5 puntos. "
                "Punto 1: 'Backend: Si' o 'Backend: No'. "
                "Punto 2: lista de elementos del HTML. "
                "Punto 3: lista de endpoints con metodo y ruta, o 'No aplica'. "
                "Punto 4: descripcion de estilos con valores concretos. "
                "Punto 5: correcciones pendientes de memory.md o 'Sin correcciones pendientes'."
            ),
            agent=planificador
        )

        tarea_backend = Task(
            description="""
Lee el plan del Planificador en el contexto de esta tarea.

REGLA ABSOLUTA: Guarda el archivo con Guardar_MainPy. La ruta resultante es app_generada/main.py.

Si el plan dice "Backend: No", genera EXACTAMENTE este main.py minimo:

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

Si el plan dice "Backend: Si", genera ese mismo esqueleto MAS los endpoints del plan.
Los endpoints de API empiezan con /api/ y devuelven diccionarios Python directamente.
""",
            expected_output=(
                "Confirmacion exacta: 'OK: main.py guardado en app_generada/main.py.' "
                "El archivo contiene: imports (FastAPI, FileResponse, StaticFiles, uvicorn, os), "
                "BASE_DIR con os.path.dirname(os.path.abspath(__file__)), "
                "app.mount('/static', StaticFiles(directory=BASE_DIR), name='static'), "
                "endpoint @app.get('/') que devuelve FileResponse(os.path.join(BASE_DIR, 'index.html')), "
                "y uvicorn.run('main:app', host='0.0.0.0', port=8001, reload=True) en __main__."
            ),
            agent=dev_backend,
            context=[tarea_plan],
        )

        tarea_frontend = Task(
            description="""
Lee el plan del Planificador en el contexto de esta tarea.

Genera index.html usando Guardar_IndexHtml. 
USA EXACTAMENTE esta estructura de <head>, sin modificar la ruta del CSS:

<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>App</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <h1>[TITULO DEL TEMA]</h1>
    [CONTENIDO SEGUN EL PLAN]
</body>
</html>

REGLA: href="/static/style.css" es una cadena fija. No la alteres.
- Plan "Backend: No" → datos directamente en el HTML, sin fetch().
- Plan "Backend: Si" → fetch('http://localhost:8001/api/ruta') extrayendo data.propiedad.
- Imagenes: URLs reales de Wikimedia Commons. Nunca picsum.photos ni example.com.
""",
            expected_output=(
                "Confirmacion exacta: 'OK: index.html guardado en app_generada/index.html.' "
                "El <head> contiene exactamente: <link rel='stylesheet' href='/static/style.css'>"
                "<h1> como primer elemento del body con titulo descriptivo "
            ),
            agent=dev_frontend,
            context=[tarea_plan],
        )

        tarea_css = Task(
            description="""
Lee el plan del Planificador en el contexto de esta tarea.

Genera style.css con las siguientes reglas base OBLIGATORIAS mas los estilos especificos del plan:

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background: #1a1a2e;
    color: #ffffff;
    font-family: sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 2rem;
}

h1 { margin-bottom: 1.5rem; font-size: 2rem; }

button {
    background: #6c63ff;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
}

button:hover { background: #574fd6; }

Anade los estilos adicionales que el plan especifique. Maximo 60 lineas total.
Guarda el archivo con Guardar_StyleCss.
""",
            expected_output=(
                "Confirmacion exacta: 'OK: style.css guardado en app_generada/style.css.' "
                "El archivo contiene: reset de box-sizing/margin/padding, "
                "body con background #1a1a2e, color #ffffff, flex centrado, "
                "h1 con margin-bottom, button con #6c63ff, button:hover con #574fd6, "
                "y estilos adicionales del plan si aplica."
            ),
            agent=dev_css,
            context=[tarea_plan],
        )

        tarea_memoria = Task(
            description=f"""
Llama a Guardar_Memory UNA SOLA VEZ con este texto exacto, sustituyendo los corchetes:

Estado actual: [que hace la app en 10 palabras]
Endpoints o elementos clave: [endpoints /api/... o elementos HTML principales]

STOP. No escribas nada mas. No hay seccion de mejoras. No hay observaciones.
El usuario pidio: {descripcion}
""",
            expected_output=(
                "Confirmacion de Guardar_Memory exitoso. "
                "Exactamente 2 lineas guardadas. "
                "linea 1 con 'Estado actual:' y "
                "linea 2 empieza con 'Endpoints o elementos clave:'."
                "Sin ninguna linea adicional."
            ),
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
        emit("finalizado", "App generada en app_generada/")

    except Exception as e:
        emit("error", f"Error: {str(e)}")


class AppRequest(BaseModel):
    descripcion: str
    sesion_id: str

class FeedbackRequest(BaseModel):
    tipo: str
    categoria: str = "General"
    descripcion: str


@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.post("/generar")
async def generar(req: AppRequest):
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    _sesiones[req.sesion_id] = q
    loop.run_in_executor(None, lanzar_crew, req.descripcion, q, loop)
    return {"ok": True}


@app.get("/progreso/{sesion_id}")
async def progreso(sesion_id: str):
    async def stream():
        for _ in range(30):
            if sesion_id in _sesiones:
                break
            yield 'data: {"tipo":"ping"}\n\n'
            await asyncio.sleep(1)
        else:
            yield 'data: {"tipo":"error","mensaje":"Sesion no encontrada"}\n\n'
            return

        q = _sesiones[sesion_id]
        try:
            while True:
                try:
                    evento = await asyncio.wait_for(q.get(), timeout=3.0)
                    data = json.dumps(evento, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    if evento["tipo"] in ["finalizado", "error"]:
                        await asyncio.sleep(0.5)
                        break
                except asyncio.TimeoutError:
                    yield 'data: {"tipo":"ping"}\n\n'
        finally:
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
            entrada = (
                f"\n\n## CORRECCION REQUERIDA ({fecha})\n"
                f"- Archivo sospechoso/Categoria: {req.categoria}\n"
                f"- Instruccion: {req.descripcion}\n"
                f"- Accion: Usa LectorTool para leer el codigo actual y aplicar esta correccion."
            )
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