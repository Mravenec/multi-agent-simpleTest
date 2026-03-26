# Sistema Multi-Agente — Alex & Sofia
## Arquitectura de Terminales Paralelas

---

## Estructura de Carpetas

```
multi-agent/
│
├── orchestrator.py          ← Terminal central (ejecutar esto primero)
├── agent_runner.py          ← Runner genérico (se lanza automáticamente)
│
├── agents/
│   ├── alex/
│   │   ├── config.json      ← Modelo, temperatura, interlocutor
│   │   ├── personality.md   ← Perfil completo de Alex
│   │   └── memory.md        ← Memoria de conversación (se actualiza sola)
│   │
│   └── sofia/
│       ├── config.json
│       ├── personality.md
│       └── memory.md
│
├── shared/
│   ├── conversation.txt     ← Historial compartido (ambos agentes escriben aquí)
│   ├── state.json           ← Estado global (turno actual, iteración)
│   └── signal.json          ← Canal de señales orquestador ↔ agentes
│
├── logs/
│   ├── orchestrator.log     ← Log del orquestador central
│   ├── alex.log             ← Log de Alex
│   └── sofia.log            ← Log de Sofia
│
└── README.md
```

---

## Cómo Funciona

### Flujo de Orquestación

```
ORQUESTADOR (terminal central)
    │
    ├─► Escribe signal.json { signal: "go", target: "alex" }
    │           │
    │           └─► TERMINAL ALEX despierta
    │                   1. Lee conversación
    │                   2. Analiza último mensaje de Sofia
    │                   3. Construye prompt con personalidad + memoria
    │                   4. Llama a Ollama
    │                   5. Limpia y publica respuesta
    │                   6. Escribe signal.json { signal: "done", target: "alex" }
    │
    ├─► Orquestador detecta "done" → muestra respuesta → pausa
    │
    ├─► Escribe signal.json { signal: "go", target: "sofia" }
    │           │
    │           └─► TERMINAL SOFIA despierta
    │                   (mismo proceso)
    │
    └─► ... repite N iteraciones → señal "stop"
```

### Comunicación (solo archivos, sin dependencias)

| Archivo            | Quién escribe       | Quién lee          |
|--------------------|---------------------|--------------------|
| `shared/signal.json` | Orquestador y agentes | Orquestador y agentes |
| `shared/state.json`  | Orquestador         | Orquestador         |
| `shared/conversation.txt` | Agentes        | Agentes + Orquestador |
| `agents/*/memory.md` | Cada agente         | Cada agente         |

---

## Requisitos

- Python 3.7+
- Ollama corriendo en `localhost:11434`
- Modelo: `qwen2.5:0.5b` (o el que configures en `config.json`)

```bash
# Instalar Ollama y bajar el modelo
ollama pull qwen2.5:0.5b
```

---

## Ejecución

```bash
# Simplemente ejecutar el orquestador
cd multi-agent
python orchestrator.py
```

El orquestador:
1. Pregunta cuántas iteraciones y pausa entre turnos
2. **Abre automáticamente** una terminal para Alex y otra para Sofia
3. Coordina los turnos en orden lógico

### Compatibilidad de Terminales

| OS      | Emulador usado                                    |
|---------|---------------------------------------------------|
| Windows | `cmd` (nativo, no requiere instalación)           |
| macOS   | `Terminal.app` (nativo, no requiere instalación)  |
| Linux   | gnome-terminal → xterm → konsole → xfce4 → lxterminal |

---

## Personalizar Agentes

### Cambiar modelo
Editar `agents/<nombre>/config.json`:
```json
{
  "model": "llama3.2:1b",
  "temperature": 0.85
}
```

### Cambiar personalidad
Editar `agents/<nombre>/personality.md` — el agente lo lee en cada turno.

### Agregar más agentes
1. Crear carpeta `agents/<nuevo>/` con `config.json`, `personality.md`, `memory.md`
2. En `orchestrator.py`, agregar el nombre a la lista `agents = ["alex", "sofia", "nuevo"]`
3. El `agent_runner.py` es genérico y funciona con cualquier nombre

---

## Monitoreo en Tiempo Real

```bash
# Ver conversación (Linux/macOS)
tail -f shared/conversation.txt

# Ver log del orquestador
tail -f logs/orchestrator.log

# Ver estado actual
cat shared/state.json
```

---

## Solución de Problemas

| Problema | Solución |
|----------|----------|
| Las terminales no abren en Linux | Instalar `xterm`: `sudo apt install xterm` |
| Timeout en respuestas | Aumentar `timeout` en `wait_for_done()` o usar modelo más pequeño |
| Respuestas contaminadas con markdown | El `clean_response()` en `agent_runner.py` maneja esto |
| Agente repite frases | La memoria en `memory.md` evita repeticiones; si persiste, borrar el archivo |
