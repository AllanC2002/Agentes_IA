# Generador de Apps con Multi-Agentes IA

Sistema de generación automática de aplicaciones web usando **CrewAI** con múltiples agentes especializados, un backend en **FastAPI** y un LLM servido por **Groq**.

---

## Funcionamiento

El usuario describe en lenguaje natural la app que quiere, y el sistema genera automáticamente tres archivos listos para ejecutar:

| Archivo | Descripción |
|---|---|
| `app_generada/main.py` | Servidor FastAPI con los endpoints necesarios |
| `app_generada/index.html` | Interfaz HTML5 |
| `app_generada/style.css` | Estilos con dark mode por defecto |

---

## Arquitectura

```
controller.py (FastAPI - puerto 8000)
│
├── POST /generar          -> Lanza el Crew
├── GET  /progreso/{id}    -> Estado de los agentes
└── POST /feedback         -> Guarda correcciones en memory.md
```

### Agentes (proceso secuencial)

```
Planificador Técnico
    Lee context.md + memory.md y produce el plan
Backend Developer (FastAPI)
    Genera main.py
Frontend Developer (HTML5)
    Genera index.html
CSS Developer
    Genera style.css
Secretario de Memoria
    Actualiza memory.md con el estado de la iteración
```

Cada agente tiene acceso solo a las herramientas que necesita, evitando que sobreescriban archivos ajenos.

---

## Herramientas personalizadas (CrewAI `BaseTool`)

| Herramienta | Descripción |
|---|---|
| `LectorTool` | Lee `context.md`, `memory.md` o archivos de `app_generada/` |
| `GuardarMainPy` | Escribe `app_generada/main.py` |
| `GuardarIndexHtml` | Escribe `app_generada/index.html` |
| `GuardarStyleCss` | Escribe `app_generada/style.css` |
| `GuardarMemory` | Agrega entradas al historial `memory.md` sin borrar lo anterior |

---

## Memoria del sistema

El proyecto usa dos archivos como memoria persistente entre iteraciones:

- **`context.md`** — Reglas fijas del sistema: tecnologías permitidas, estructura obligatoria del `main.py`, reglas de CSS, etc. El Planificador lo lee primero antes de tomar cualquier decisión.
- **`memory.md`** — Historial acumulativo de ejecuciones. Se actualiza al final de cada generación y también recibe el feedback del usuario (correcciones y observaciones).

---

## Flujo de una generación

```
1. Usuario envía POST /generar { descripcion, sesion_id }
2. Se crea una asyncio.Queue para esa sesión
3. lanzar_crew() se ejecuta en un hilo via run_in_executor()
4. El frontend conecta a GET /progreso/{sesion_id}
5. Los agentes ejecutan sus tareas secuencialmente:
   Planificador -> Backend -> Frontend -> CSS -> Secretario
6. Al finalizar, se emite evento "finalizado" y se limpia la sesión
```

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd <carpeta>

# 2. Crear entorno virtual e instalar dependencias
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

pip install fastapi uvicorn crewai litellm python-dotenv

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env y agregar tu GROQ_API_KEY
```
### `.env`
```env
GROQ_API_KEY=gsk_...
```
---
## Ejecución

```bash
python controller.py
```
El servidor arranca en `http://localhost:8000`. Abre esa URL en el navegador para acceder al frontend generador.

La app generada (en `app_generada/`) se sirve directamente desde la ruta `/static/` del mismo servidor.

---

## Endpoints de la API

### `POST /generar`
Inicia la generación de la app.

```json
{
  "descripcion": "Una app que muestre la tabla de posiciones de la Premier League",
  "sesion_id": "abc123"
}
```

### `GET /progreso/{sesion_id}`
Eventos de progreso. Tipos de evento:

| `tipo` | Descripción |
|---|---|
| `ping` | Heartbeat mientras se espera |
| `inicio` | La crew comenzó a ejecutarse |
| `agente` | Mensaje de progreso de un agente |
| `finalizado` | Generación completada con éxito |
| `error` | Ocurrió un error durante la generación |

### `POST /feedback`
Guarda feedback del usuario en `memory.md` para que los agentes lo consideren en la próxima iteración.

```json
{
  "tipo": "mejora",
  "categoria": "style.css",
  "descripcion": "El botón no tiene suficiente contraste en pantallas pequeñas"
}
```
---

## Configuración del LLM

El sistema usa **Groq** con el modelo `llama-3.3-70b-versatile` vía `litellm`:

```python
llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0,
    max_retries=5,
    timeout=60,
)
```
`litellm` maneja automáticamente los reintentos (máx. 5, con 15 segundos de espera entre cada uno) para tolerar timeouts o throttling del proveedor.

---
## Estructura del proyecto

```
.
├── controller.py        # Servidor principal FastAPI + lógica multi-agente
├── context.md           # Reglas del sistema (auto-creado si no existe)
├── memory.md            # Historial de iteraciones (auto-creado si no existe)
├── index.html           # Frontend del generador
├── style.css            # Estilos del frontend del generador
├── app_generada/        # Salida: archivos de la app solicitada
│   ├── main.py
│   ├── index.html
│   └── style.css
└── app_debug.log        # Log de depuración
```
---
## Notas técnicas
- El `max_rpm=2` en la Crew limita las peticiones al LLM a 2 por minuto para evitar rate limits de Groq.
- El planificador tiene `max_iter=4`; los demás agentes tienen `max_iter=3` o `2` para evitar bucles costosos.