# MANUAL DE DESARROLLO (Reglas Estrictas)
## 1. Stack Tecnológico
- Backend: FastAPI (Python) + Uvicorn.
- Frontend: HTML5 + CSS3 + Vanilla JS.
- Archivos permitidos: `main.py`, `index.html`, `style.css` (ubicados en `app_generada/`).

## 2. Reglas de Backend (main.py)
- Importaciones obligatorias:
  `from fastapi import FastAPI`
  `from fastapi.responses import FileResponse, JSONResponse`
  `from fastapi.staticfiles import StaticFiles`
  `import uvicorn, os`
- Montaje estático: `app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")`
- Endpoint Raíz: `@app.get("/")` debe devolver obligatoriamente `FileResponse(os.path.join(BASE_DIR, "index.html"))`.
- Endpoints API: Deben empezar con `/api/` y devolver diccionarios (JSON).
- Ejecución: Siempre usar `uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)`

## 3. Reglas de Frontend y CSS
- Enlazar CSS siempre como: `<link rel="stylesheet" href="/static/style.css">`
- Peticiones (Fetch): Deben usar URLs absolutas apuntando al puerto correcto. Ejemplo: `fetch('http://localhost:8001/api/datos')`.
- Manejo de JSON: Nunca asigne objetos completos a `textContent`. Extraiga la propiedad específica (ej. `data.mensaje`).
- Diseño: Siempre usar una paleta Dark Mode (#1a1a2e para fondo, #ffffff para texto).

## 4. Flujo de Trabajo (¡CRÍTICO!)
- Si el requerimiento es puramente ESTÁTICO (ej. mostrar capital de Ecuador), NO crees endpoints `/api/`, pon la información directo en el HTML.