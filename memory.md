# Memoria de Aprendizaje
Este archivo almacena lecciones críticas aprendidas de errores pasados. No es un log de ejecución.

## Errores corregidos históricamente (NO REPETIR)
1. **Error de Fetch:** El frontend fallaba al hacer peticiones relativas. *Solución:* Todas las llamadas fetch() deben usar la ruta completa: `http://localhost:8001/api/..`
2. **Backend innecesario:** Se creaba lógica de API para datos que nunca cambian. *Solución:* Si la app solo muestra información fija (ej. datos de un país), haz un HTML estático puro, sin endpoints de FastAPI extra.
3. **Objetos en el DOM:** Se intentaba pintar JSON directamente. *Solución:* Usar `data.propiedad` en lugar de imprimir `[object Object]`.
4. **Archivos CSS desconectados:** *Solución:* El endpoint raíz siempre sirve index.html, y este siempre debe tener `<link rel="stylesheet" href="style.css">`.
5. **APIs externas:** *Solución:* Si necesitan una api key, evitar el uso de las mismas.

## Sugerencias del usuario pendientes:


## Iteración 2026-05-19 14:06
Se creó una aplicación simple que muestra la hora actual. Se generaron los archivos main.py, index.html y style.css. Se creó un endpoint /api/hora que devuelve la hora actual en formato JSON. No se utilizaron recursos externos. La aplicación se puede mejorar agregando más funcionalidades o mejorando la interfaz de usuario.