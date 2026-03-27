# Sistema Multi-Agente v2 — Alex & Sofia aprobada
## Arquitectura de 3 Instancias Ollama Independientes

---

## ¿Por qué 3 instancias?

En la versión anterior, un solo Ollama atendía a ambos agentes. Esto causaba:
- **Contaminación de contexto**: la memoria interna de Ollama "filtraba" entre agentes
- **Loops de repetición**: el modelo repetía respuestas del agente anterior
- **Pérdida de personalidad**: los agentes adoptaban frases del otro

**Solución v2**: cada proceso tiene su propio servidor Ollama en un puerto distinto:

```
  Puerto 11434 → Árbitro  (evalúa respuestas, temperatura 0.3 — severo)
  Puerto 11435 → Alex     (genera respuestas, temperatura 0.85)
  Puerto 11436 → Sofia    (genera respuestas, temperatura 0.90)
```

Cada instancia tiene contexto completamente aislado. Lo que "piensa" Alex no contamina a Sofia.

---

## Estructura de Carpetas

```
multi-agent/
│
├── orchestrator.py       ← Punto de entrada. Coordina turnos + árbitro
├── agent_runner.py       ← Runner genérico para cada agente
├── arbiter.py            ← Módulo árbitro (evalúa calidad de respuestas)
│
├── agents/
│   ├── alex/
│   │   ├── config.json   ← { "ollama_port": 11435, "model": "qwen2.5:1.5b", ... }
│   │   ├── personality.md
│   │   └── memory.md     ← Se actualiza automáticamente (solo respuestas propias)
│   │
│   └── sofia/
│       ├── config.json   ← { "ollama_port": 11436, "model": "qwen2.5:1.5b", ... }
│       ├── personality.md
│       └── memory.md
│
├── shared/
│   ├── conversation.txt  ← Historial compartido (ambos agentes leen aquí)
│   ├── state.json        ← Estado global (turno, iteración)
│   ├── signal.json       ← Canal de señales orquestador ↔ agentes
│   └── arbiter.json      ← Canal de señales árbitro → agentes
│
└── logs/
    ├── orchestrator.log
    ├── arbiter.log       ← NUEVO: log de decisiones del árbitro
    ├── alex.log
    └── sofia.log
```

---

## Flujo Completo de un Turno

```
ORQUESTADOR
    │
    ├─► signal.json { signal: "go", target: "alex" }
    │           │
    │           └─► ALEX (puerto 11435)
    │                   1. Lee shared/conversation.txt
    │                   2. Lee agents/alex/memory.md (sus propias respuestas anteriores)
    │                   3. Construye prompt con personalidad + anti-repetición
    │                   4. Llama a localhost:11435/api/generate (SU Ollama)
    │                   5. Limpia respuesta
    │                   6. Verifica similitud con su memoria
    │                   7. signal.json { signal: "done", response: "...", target: "alex" }
    │
    ├─► ÁRBITRO (puerto 11434) evalúa la respuesta:
    │       - Reglas rápidas: ¿es de IA? ¿repite? ¿muy corta?
    │       - Ollama semántico: ¿coherente con el personaje y contexto?
    │
    │   SI acepta:
    │       ├─► Escribe respuesta en shared/conversation.txt
    │       └─► Pasa al siguiente agente (Sofia)
    │
    │   SI rechaza:
    │       ├─► Escribe razón + sugerencia en shared/arbiter.json
    │       ├─► signal.json { signal: "go", target: "alex" } (reintento)
    │       └─► Alex lee el feedback, genera nueva respuesta
    │           (máximo 2 rechazos → usa fallback)
    │
    └─► ... repite para Sofia → ... N iteraciones → signal "stop"
```

---

## Configuración: 3 Instancias de Ollama

### Opción A (Recomendada): 3 terminales separadas

```bash
# Terminal 1 — Árbitro
OLLAMA_HOST=0.0.0.0:11434 ollama serve

# Terminal 2 — Alex
OLLAMA_HOST=0.0.0.0:11435 ollama serve

# Terminal 3 — Sofia
OLLAMA_HOST=0.0.0.0:11436 ollama serve
```

> En Windows usa `set` en vez de `export`:
> ```cmd
> set OLLAMA_HOST=0.0.0.0:11435 && ollama serve
> ```

Asegúrate de tener el modelo descargado en cada instancia:
```bash
ollama pull qwen2.5:1.5b
```

### Opción B (Fallback): 1 sola instancia

Si solo tienes 1 Ollama corriendo en el puerto 11434, el sistema lo detecta automáticamente
y usa ese puerto para todos. Funciona, pero los agentes comparten contexto.
El sistema imprime una advertencia pero no falla.

---

## Ejecución

```bash
cd multi-agent
python orchestrator.py
```

El orquestador:
1. Muestra la arquitectura de puertos
2. Pide iteraciones y pausa entre turnos
3. Abre terminales para Alex y Sofia automáticamente
4. Coordina turnos con evaluación del árbitro

---

## Monitoreo en Tiempo Real

```bash
# Conversación (Linux/macOS)
tail -f shared/conversation.txt

# Decisiones del árbitro
tail -f logs/arbiter.log

# Estado general
cat shared/state.json

# Ver qué rechazó el árbitro
cat shared/arbiter.json
```

---

## Personalización

### Cambiar modelo por agente
Editar `agents/<nombre>/config.json`:
```json
{
  "model": "llama3.2:1b",
  "ollama_port": 11435,
  "temperature": 0.85
}
```

### Ajustar severidad del árbitro
En `arbiter.py`, cambiar `ARBITER_CONFIG`:
```python
ARBITER_CONFIG = {
    "temperature": 0.1,   # Más bajo = más estricto
}
```

O modificar los umbrales de similitud:
```python
# En quick_reject / repetition_reject:
sim > 0.6  # Umbral de Jaccard (0-1). Más bajo = más estricto
```

### Agregar un tercer agente
1. Crear `agents/<nombre>/` con `config.json` (nuevo `ollama_port`), `personality.md`, `memory.md`
2. En `orchestrator.py`, añadir a `agents = ["alex", "sofia", "nombre"]`
3. `agent_runner.py` es genérico y funciona con cualquier nombre

---

## Solución de Problemas

| Problema | Causa | Solución |
|----------|-------|----------|
| Agente se queda esperando | Ollama no activo en su puerto | Verificar `OLLAMA_HOST=... ollama serve` |
| Loops de repetición | Un solo Ollama compartido | Levantar 3 instancias separadas |
| Árbitro rechaza todo | Temperatura muy baja o modelo confundido | Subir `temperature` en `ARBITER_CONFIG` |
| Terminal no se abre en Linux | Sin emulador compatible | `sudo apt install xterm` |
| Timeout frecuente | Hardware lento con modelo grande | Usar modelo más pequeño: `qwen2.5:0.5b` |

---

## Requisitos

- Python 3.7+
- Ollama instalado
- Modelo `qwen2.5:1.5b` (u otro compatible)
- (Recomendado) 3 terminales para instancias Ollama separadas

```bash
ollama pull qwen2.5:1.5b
```
