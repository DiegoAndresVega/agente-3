---
name: No arrancar el servidor en background
description: No lanzar test_server.py en background — deja procesos huérfanos que el usuario no puede cerrar con Ctrl+C
type: feedback
originSessionId: 441ddfe6-87cf-4769-b8c1-1dce5dcab318
---
Nunca arrancar `test_server.py` con `run_in_background: true`. Esto crea procesos `python3.13` huérfanos independientes del terminal del usuario — Ctrl+C en su terminal no los mata, y hay que buscar el PID y matarlo con PowerShell.

**Why:** Ocurrió varias veces en sesión — procesos quedaron vivos en puerto 5000 aunque el usuario cerró el terminal.

**How to apply:** Cuando se necesite reiniciar el servidor, decirle al usuario que lo haga él desde su terminal con `python test_server.py`. No usar `run_in_background: true` para servidores Flask.
