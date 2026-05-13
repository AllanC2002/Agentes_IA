import os
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool
from dotenv import load_dotenv
load_dotenv()

import litellm
litellm.request_timeout = 60
litellm.num_retries = 5
litellm.retry_after = 10
# ─────────────────────────────────────────────
# HERRAMIENTAS
# ─────────────────────────────────────────────
class LectorTool(BaseTool):
    name: str = "Lector_de_Archivos"
    description: str = "Lee un archivo local. Parámetro: filename (nombre del archivo, ej: context.md)."

    def _run(self, filename: str) -> str:
        try:
            clean = os.path.basename(filename)
            if not os.path.exists(clean):
                return f"ADVERTENCIA: '{clean}' no existe."
            with open(clean, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error al leer: {str(e)}"

class EscritorTool(BaseTool):
    name: str = "Escritor_de_Archivos"
    description: str = (
        "Guarda contenido en un archivo. "
        "Parámetros: filename (ej: main.py o ../memory.md) y content (texto completo)."
    )

    def _run(self, filename: str, content: str) -> str:
        try:
            # Permite escribir en raíz con ../ o directo
            if filename.startswith("../"):
                filepath = filename  # memory.md en raíz
            else:
                os.makedirs("app_generada", exist_ok=True)
                filepath = os.path.join("app_generada", os.path.basename(filename))

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return f"OK: '{filepath}' guardado."
        except Exception as e:
            return f"Error: {str(e)}"

# ─────────────────────────────────────────────
# ARCHIVOS INICIALES
# ─────────────────────────────────────────────
if not os.path.exists("context.md"):
    with open("context.md", "w") as f:
        f.write("""# Contexto del Proyecto
Aplicación web simple con FastAPI.
- Un endpoint GET /  que sirve el index.html
- Un endpoint GET /api/saludo que retorna JSON {"mensaje": "Hola desde la API"}
- HTML con formulario que llama al endpoint y muestra la respuesta
- CSS moderno, dark mode, centrado
""")

if not os.path.exists("memory.md"):
    with open("memory.md", "w") as f:
        f.write("# Memoria del Agente\nIteración 0: Sin ejecuciones previas.\n")

# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────
llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    api_key=os.environ.get("GROQ_API_KEY"),
    temperature=0,
    max_retries=5,        # Reintenta automáticamente
    timeout=60,
)

lector = LectorTool()
escritor = EscritorTool()

# ─────────────────────────────────────────────
# AGENTES
# ─────────────────────────────────────────────
arquitecto = Agent(
    role="Arquitecto de Software",
    goal="Leer el contexto y memoria, y producir un plan técnico detallado.",
    backstory="Analizas requerimientos y defines qué debe construirse exactamente.",
    llm=llm,
    tools=[lector],
    verbose=True,
    max_iter=5,
)

backend_dev = Agent(
    role="Desarrollador Backend",
    goal="Generar main.py con FastAPI según el plan arquitectónico.",
    backstory="Escribes APIs limpias en Python. Usas el plan del arquitecto como guía.",
    llm=llm,
    tools=[escritor],
    verbose=True,
    max_iter=5,
)

frontend_dev = Agent(
    role="Desarrollador Frontend HTML",
    goal="Generar index.html según el plan arquitectónico.",
    backstory="Construyes interfaces web semánticas y funcionales.",
    llm=llm,
    tools=[escritor],
    verbose=True,
    max_iter=5,
)

css_dev = Agent(
    role="Diseñador CSS",
    goal="Generar style.css con diseño moderno dark mode.",
    backstory="Creas estilos limpios, responsivos y visualmente atractivos.",
    llm=llm,
    tools=[escritor],
    verbose=True,
    max_iter=5,
)

secretario = Agent(
    role="Secretario Técnico",
    goal="Actualizar memory.md en la raíz con el resumen de esta iteración.",
    backstory="Documentas lo que se construyó para que futuras iteraciones tengan contexto.",
    llm=llm,
    tools=[escritor],
    verbose=True,
    max_iter=5,
)

# ─────────────────────────────────────────────
# TAREAS
# ─────────────────────────────────────────────
tarea_arquitecto = Task(
    description="""
Usa Lector_de_Archivos para leer 'context.md' y luego 'memory.md'.
Con esa información, produce un plan técnico que incluya:
1. Endpoints a implementar en FastAPI
2. Estructura del HTML
3. Estilos CSS a aplicar
NO uses herramientas más de lo necesario. Tu output es solo el plan en texto.
""",
    expected_output="Plan técnico detallado con endpoints, estructura HTML y estilos CSS.",
    agent=arquitecto,
)

tarea_backend = Task(
    description="""
Basándote en el plan del arquitecto (disponible en el contexto),
usa Escritor_de_Archivos para guardar 'main.py' con:
- FastAPI app
- Endpoint GET / que sirve index.html desde la carpeta app_generada/
- Endpoint GET /api/saludo que retorna JSON
- Configuración de archivos estáticos para servir style.css
El archivo debe ser funcional y listo para ejecutar con: uvicorn main:app
""",
    expected_output="Confirmación de que main.py fue guardado exitosamente.",
    agent=backend_dev,
    context=[tarea_arquitecto],
)

tarea_frontend = Task(
    description="""
Basándote en el plan del arquitecto,
usa Escritor_de_Archivos para guardar 'index.html' con:
- Estructura HTML5 completa
- Link a /static/style.css
- Un botón que llame a /api/saludo via fetch()
- Un div que muestre la respuesta de la API
""",
    expected_output="Confirmación de que index.html fue guardado exitosamente.",
    agent=frontend_dev,
    context=[tarea_arquitecto],
)

tarea_css = Task(
    description="""
Basándote en el plan del arquitecto,
usa Escritor_de_Archivos para guardar 'style.css' con:
- Dark mode (fondo #1a1a2e, texto claro)
- Diseño centrado con max-width
- Botón con hover effect
- Tipografía moderna (usa Google Fonts: Inter)
""",
    expected_output="Confirmación de que style.css fue guardado exitosamente.",
    agent=css_dev,
    context=[tarea_arquitecto],
)

tarea_secretario = Task(
    description="""
Usa Escritor_de_Archivos para actualizar '../memory.md' (en la raíz, no en app_generada).
Escribe un resumen de esta iteración incluyendo:
- Qué archivos se generaron
- Qué endpoints tiene la app
- Fecha simulada: iteración actual
Conserva el historial previo y agrega la nueva entrada al final.
""",
    expected_output="Confirmación de que memory.md fue actualizado en la raíz.",
    agent=secretario,
    context=[tarea_backend, tarea_frontend, tarea_css],
)

# ─────────────────────────────────────────────
# CREW — secuencial para que se pasen contexto
# ─────────────────────────────────────────────
crew = Crew(
    agents=[arquitecto, backend_dev, frontend_dev, css_dev, secretario],
    tasks=[tarea_arquitecto, tarea_backend, tarea_frontend, tarea_css, tarea_secretario],
    process=Process.sequential,
    verbose=True,
)

result = crew.kickoff()
print("\n✅ App generada en carpeta 'app_generada/'")
print("▶️  Para correrla: cd app_generada && uvicorn main:app --reload")