# Memoria de Aprendizaje
Este archivo almacena lecciones críticas aprendidas de errores pasados. No es un log de ejecución.

## Errores corregidos históricamente (NO REPETIR)
1. **Error de Fetch:** El frontend fallaba al hacer peticiones relativas. *Solución:* Todas las llamadas fetch() deben usar la ruta completa: `http://localhost:8001/api/..`
2. **Backend innecesario:** Se creaba lógica de API para datos que nunca cambian. *Solución:* Si la app solo muestra información fija (ej. datos de un país), haz un HTML estático puro, sin endpoints de FastAPI extra.
3. **Objetos en el DOM:** Se intentaba pintar JSON directamente. *Solución:* Usar `data.propiedad` en lugar de imprimir `[object Object]`.
4. **Archivos CSS desconectados:** *Solución:* El endpoint raíz siempre sirve index.html, y este siempre debe tener `<link rel="stylesheet" href="style.css">`.
5. **APIs externas:** *Solución:* Si necesitan una api key, evitar el uso de las mismas.

## Sugerencias del usuario pendientes:

## Iteración 2026-05-19 19:37
Usuario pidió: aplicacion simple que me de una informacion de allan poe es decir solo el nombre completo y su edad, no agregues endpoints innecesarios. Archivos generados: main.py, index.html, style.css. Endpoints creados: /. Recursos externos usados: none. Qué se podría mejorar: agregar más información sobre Allan Poe o implementar una base de datos para almacenar la información.

## Feedback 2026-05-19 19:39
- App: En la parte de Html, sugiero siempre empezar con un titulo referente al tema en el body

## Iteración 2026-05-19 19:42
Se agregó un título referente al tema en el body de index.html. Archivos generados: index.html, style.css. Endpoints creados: /. Recursos externos usados: none. Mejora sugerida: Empezar con un título referente al tema en el body. Se aplicó la mejora en la categoría Frontend (index.html).

## Feedback 2026-05-19 19:47
- App: Falto la informacion de la edad y una obra representativa, con respecto a Allan poe

## Iteración 2026-05-19 19:51
Se agregó la información de la edad y una obra representativa de Allan Poe en el archivo index.html. Se mejoró la presentación en la categoría Frontend. Archivos generados: index.html, style.css. Endpoints creados: / (root). Recursos externos usados: none. Mejoras posibles: agregar más obras de Allan Poe, mejorar la interfaz de usuario.