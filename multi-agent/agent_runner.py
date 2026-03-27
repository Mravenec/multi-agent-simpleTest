"""
agent_runner.py — Terminal Independiente de Agente
====================================================
Cada agente corre en su PROPIO proceso y conecta a su PROPIO puerto de Ollama.
Esto garantiza independencia total de contexto entre Alex y Sofia.

Uso:
    python agent_runner.py alex
    python agent_runner.py sofia

Puertos por defecto:
    Alex  → localhost:11435
    Sofia → localhost:11436

Para levantar instancias separadas de Ollama:
    OLLAMA_HOST=0.0.0.0:11435 ollama serve   (en terminal 1)
    OLLAMA_HOST=0.0.0.0:11436 ollama serve   (en terminal 2)
"""

import sys
import os
import json
import time
import re
import urllib.request
import urllib.error
from datetime import datetime

# ─────────────────────────────────────────────────────────────
#  COLORES ANSI
# ─────────────────────────────────────────────────────────────
def supports_color():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

USE_COLOR = supports_color()

PALETTES = {
    "alex": {
        "header": "\033[94m",   # Azul
        "think":  "\033[96m",   # Cyan
        "speak":  "\033[97m",   # Blanco brillante
        "dim":    "\033[90m",   # Gris
        "ok":     "\033[92m",   # Verde
        "err":    "\033[91m",   # Rojo
        "warn":   "\033[93m",   # Amarillo
        "reset":  "\033[0m",
    },
    "sofia": {
        "header": "\033[95m",   # Magenta
        "think":  "\033[93m",   # Amarillo
        "speak":  "\033[97m",   # Blanco brillante
        "dim":    "\033[90m",   # Gris
        "ok":     "\033[92m",   # Verde
        "err":    "\033[91m",   # Rojo
        "warn":   "\033[33m",   # Naranja
        "reset":  "\033[0m",
    },
}

def c(agent, key, text):
    if not USE_COLOR:
        return text
    palette = PALETTES.get(agent, PALETTES["alex"])
    return f"{palette.get(key, '')}{text}{palette['reset']}"


# ─────────────────────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Si se ejecuta desde subdirectorio, sube hasta encontrar /shared
while not os.path.exists(os.path.join(BASE_DIR, "shared")) and \
      BASE_DIR != os.path.dirname(BASE_DIR):
    BASE_DIR = os.path.dirname(BASE_DIR)

def paths(agent_name):
    return {
        "config":       os.path.join(BASE_DIR, "agents", agent_name, "config.json"),
        "personality":  os.path.join(BASE_DIR, "agents", agent_name, "personality.md"),
        "memory":       os.path.join(BASE_DIR, "agents", agent_name, "memory.md"),
        "conversation": os.path.join(BASE_DIR, "shared", "conversation.txt"),
        "state":        os.path.join(BASE_DIR, "shared", "state.json"),
        "signal":       os.path.join(BASE_DIR, "shared", "signal.json"),
        "arbiter":      os.path.join(BASE_DIR, "shared", "arbiter.json"),
        "log":          os.path.join(BASE_DIR, "logs", f"{agent_name}.log"),
    }


# ─────────────────────────────────────────────────────────────
#  UTILIDADES DE ARCHIVO
# ─────────────────────────────────────────────────────────────
def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def append_text(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)

def log(agent_name, message):
    p = paths(agent_name)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(p["log"]), exist_ok=True)
    with open(p["log"], "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")


# ─────────────────────────────────────────────────────────────
#  OLLAMA — CONEXIÓN INDEPENDIENTE POR AGENTE
# ─────────────────────────────────────────────────────────────
def check_ollama(port):
    """Verifica si el servidor Ollama está activo en el puerto dado."""
    url = f"http://localhost:{port}/api/tags"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False

def call_ollama(port, model, system_prompt, user_prompt, temperature=0.85, max_retries=3):
    """
    Llama al Ollama en el puerto específico de este agente.
    Cada agente tiene su propia instancia → contexto completamente aislado.
    """
    url = f"http://localhost:{port}/api/generate"
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.92,
            "top_k": 40,
            "num_predict": 150,
            "repeat_penalty": 1.3,        # Penaliza fuertemente la repetición
            "repeat_last_n": 64,           # Ventana para detectar repeticiones
            "stop": [
                "Alex:", "Sofia:", "ALEX:", "SOFIA:",
                "assistant:", "User:", "Sistema:",
                "\n\n\n",
            ]
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                if resp.status == 200:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result.get("response", "").strip()
                return f"[HTTP_ERROR:{resp.status}]"
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                time.sleep(1.5)
            else:
                return f"[CONNECTION_ERROR:{e}]"
        except Exception as e:
            return f"[ERROR:{e}]"
    return ""


# ─────────────────────────────────────────────────────────────
#  GESTIÓN DE MEMORIA PROPIA DEL AGENTE
# ─────────────────────────────────────────────────────────────
def load_own_memory(p, n=8):
    """
    Carga las últimas N respuestas propias del agente desde su memory.md.
    Esta memoria es EXCLUSIVA de este agente — no la ve el otro.
    """
    raw = read_text(p["memory"])
    lines = []
    for line in raw.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("_") and \
           not line.startswith("##") and len(line) > 8:
            # Extraer solo el texto, sin timestamps
            clean = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line).strip()
            if clean:
                lines.append(clean)
    return lines[-n:]

def save_to_memory(agent_name, response, p):
    """Guarda la respuesta del agente en su memoria privada."""
    ts = datetime.now().strftime("%H:%M:%S")
    append_text(p["memory"], f"[{ts}] {response}\n")

def jaccard_similarity(str1, str2):
    """Similitud de Jaccard entre dos strings."""
    s1 = set(str1.lower().split())
    s2 = set(str2.lower().split())
    if not s1 or not s2:
        return 0.0
    inter = len(s1 & s2)
    union = len(s1 | s2)
    return inter / union if union > 0 else 0.0

def is_too_similar_to_memory(response, memory_lines, threshold=0.55):
    """
    Verifica si la respuesta es demasiado similar a algo ya dicho.
    Umbral más bajo = más estricto contra repeticiones.
    """
    r_lower = response.lower()
    for mem in memory_lines:
        sim = jaccard_similarity(r_lower, mem.lower())
        if sim > threshold:
            return True, mem, sim
    return False, "", 0.0

def is_too_similar_to_conversation(response, conversation_entries, threshold=0.5):
    """Verifica si la respuesta repite algo de la conversación reciente."""
    r_lower = response.lower()
    for entry in conversation_entries[-6:]:
        sim = jaccard_similarity(r_lower, entry["message"].lower())
        if sim > threshold:
            return True, entry["message"], sim
    return False, "", 0.0


# ─────────────────────────────────────────────────────────────
#  PARSEO DE CONVERSACIÓN COMPARTIDA
# ─────────────────────────────────────────────────────────────
def parse_conversation(raw_text, n=8):
    """
    Extrae los últimos N mensajes del archivo compartido de conversación.
    Formato: [HH:MM:SS] AGENTE:\nmensaje
    """
    entries = []
    blocks = re.split(r'\n(?=\[\d{2}:\d{2}:\d{2}\])', raw_text)
    for block in blocks:
        block = block.strip()
        m = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s+(ALEX|SOFIA):\s*\n?(.*)', block, re.DOTALL)
        if m:
            t, agent, msg = m.groups()
            # Tomar solo la primera línea no vacía del mensaje
            msg_lines = [l.strip() for l in msg.strip().split("\n") if l.strip()]
            msg_clean = msg_lines[0] if msg_lines else ""
            # Limpiar comillas residuales
            msg_clean = msg_clean.strip('"').strip("'").strip()
            if msg_clean and len(msg_clean) > 3:
                entries.append({
                    "time": t,
                    "agent": agent.lower(),
                    "message": msg_clean
                })
    return entries[-n:]

def get_last_message_from(conversation_entries, from_agent):
    """Obtiene el último mensaje de un agente específico."""
    for entry in reversed(conversation_entries):
        if entry["agent"] == from_agent:
            return entry["message"]
    return ""

def update_conversation(agent_name, response, p):
    """Escribe la respuesta del agente al archivo compartido de conversación."""
    ts = datetime.now().strftime("%H:%M:%S")
    append_text(p["conversation"], f"\n\n[{ts}] {agent_name.upper()}:\n{response}\n")


# ─────────────────────────────────────────────────────────────
#  SEÑALES DEL ORQUESTADOR
# ─────────────────────────────────────────────────────────────
def wait_for_my_turn(agent_name, p):
    """
    Bloquea hasta que el orquestador mande señal 'go' a este agente.
    Retorna True si es su turno, False si hay señal de stop.
    """
    while True:
        try:
            sig = read_json(p["signal"])
            if sig.get("signal") == "stop":
                return False
            if sig.get("signal") == "go" and sig.get("target_agent") == agent_name:
                return True
        except Exception:
            pass
        time.sleep(0.3)

def signal_done(agent_name, response, p):
    """Señala al orquestador que este agente terminó su turno."""
    write_json(p["signal"], {
        "signal": "done",
        "target_agent": agent_name,
        "response": response,
        "timestamp": datetime.now().isoformat()
    })

def check_arbiter_feedback(agent_name, p):
    """
    Lee el archivo arbiter.json para ver si el árbitro rechazó la respuesta.
    Retorna: (rejected: bool, reason: str, suggestion: str)
    """
    try:
        if not os.path.exists(p["arbiter"]):
            return False, "", ""
        arb = read_json(p["arbiter"])
        if arb.get("target_agent") == agent_name and arb.get("verdict") == "reject":
            return True, arb.get("reason", ""), arb.get("suggestion", "")
    except Exception:
        pass
    return False, "", ""


# ─────────────────────────────────────────────────────────────
#  LIMPIEZA DE RESPUESTA
# ─────────────────────────────────────────────────────────────
FORBIDDEN_PHRASES = [
    # Saludos
    "hola", "buenos días", "buenas tardes", "buen día",
    # Frases de IA / asistente
    "como asistente", "como ia", "soy una ia", "soy un modelo",
    "inteligencia artificial", "modelo de lenguaje", "qwen",
    "estoy aquí para ayudar", "puedo ayudarte",
    # Frases de disculpa de chatbot
    "lo siento mucho por el malentendido",
    "aprecio tu preocupación",
    "gracias por entenderlo",
    "estaré encantad",
    # Salirse del personaje
    "no puedo continuar", "no puedo decir", "podría dañar",
    "confianza y seguridad en nuestra relación",
]

def clean_response(raw, agent_name):
    """
    Limpia el texto generado:
    - Elimina markdown
    - Elimina artefactos de personalidad filtrados
    - Elimina timestamps residuales
    - Verifica frases prohibidas
    - Valida longitud
    """
    text = raw.strip()
    if not text:
        return ""

    # Eliminar bloque markdown completo si hay headers
    text = re.sub(r'#{1,6}[^\n]*', '', text)
    text = re.sub(r'\*\*.*?\*\*', '', text, flags=re.DOTALL)
    text = re.sub(r'\*[^*]*\*', '', text)
    text = re.sub(r'`[^`]*`', '', text)

    # Eliminar secciones de personalidad que el modelo puede "filtrar"
    persona_headers = [
        "Perfil:", "Fondo Personal", "Esencia", "Deseos Profundos",
        "Estilo de Comunicación", "Voz Natural", "REGLAS ABSOLUTAS",
        "Tono:", "Ritmo:", "Temas favoritos:", "Evito:", "PROHIBIDO",
        "personality", "memory", "## "
    ]
    for header in persona_headers:
        idx = text.find(header)
        if idx != -1:
            text = text[:idx]

    # Eliminar timestamps residuales
    text = re.sub(r'\[\d{2}:\d{2}:\d{2}\]\s*', '', text)
    text = re.sub(r'\[\d{4}-\d{2}-\d{2}.*?\]', '', text, flags=re.DOTALL)

    # Eliminar prefijos "AgentName:" al inicio
    text = re.sub(rf'^{re.escape(agent_name)}[:\s]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(Alex|Sofia|ALEX|SOFIA)[:\s]+', '', text)

    # Normalizar whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip().strip('"').strip("'").strip()

    # Tomar solo las primeras 2 frases para no exceder el límite de personaje
    sentences = re.split(r'(?<=[.!?…])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) > 3:
        text = " ".join(sentences[:2])

    # Verificar frases prohibidas
    text_lower = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in text_lower:
            return ""

    # Verificar que no se auto-referencie como el otro agente
    other = "sofia" if agent_name == "alex" else "alex"
    if re.search(rf'\bsoy\s+{other}\b', text_lower):
        return ""

    # Verificar que hable como humano
    if re.search(r'\b(ayudarte|brindar(te)?|asistirte|proporcionarte)\b', text_lower):
        return ""

    # Validar longitud final
    if len(text) < 8 or len(text) > 400:
        return ""

    return text


# ─────────────────────────────────────────────────────────────
#  CONSTRUCCIÓN DEL PROMPT DEL AGENTE
# ─────────────────────────────────────────────────────────────
def build_agent_prompt(agent_name, config, p, conversation_entries,
                       last_message, own_memory, arbiter_suggestion=""):
    personality = read_text(p["personality"])
    interlocutor = config["interlocutor"]

    # Historial de conversación (últimos 5 turnos, bien formateado)
    history_lines = []
    for entry in conversation_entries[-5:]:
        speaker = entry["agent"].capitalize()
        history_lines.append(f"{speaker}: {entry['message']}")
    history_text = "\n".join(history_lines) if history_lines else "(inicio de la conversación)"

    # Memoria propia reciente (para evitar repetición)
    memory_text = "\n".join(f"- {m}" for m in own_memory[-6:]) if own_memory else "(sin mensajes previos)"

    # Instrucción extra si el árbitro rechazó
    arbiter_instruction = ""
    if arbiter_suggestion:
        arbiter_instruction = f"""
⚠ INSTRUCCIÓN ESPECIAL (el árbitro rechazó tu respuesta anterior):
- Razón del rechazo: {arbiter_suggestion}
- Debes crear una respuesta COMPLETAMENTE diferente
- NO uses ninguna frase de tus intentos anteriores
"""

    system_prompt = f"""Eres {agent_name.capitalize()}, una persona real en una conversación de citas con {interlocutor.capitalize()}.

{personality}

═══════════════════════════════════════════════════
REGLAS CRÍTICAS DE ESTE TURNO:
═══════════════════════════════════════════════════

1. IDENTIDAD: Eres SOLO {agent_name.capitalize()}. Nunca {interlocutor.capitalize()}.
   Nunca un asistente, IA, o personaje de ficción.

2. RESPONDE AL MENSAJE: Tu única tarea es responder al último mensaje de {interlocutor.capitalize()}.
   Si hay una pregunta → respóndela PRIMERO.
   Si es una afirmación → reacciona con tu estilo y añade algo nuevo.

3. ANTI-REPETICIÓN (CRÍTICO):
   - NUNCA copies o repitas frases de tu memoria anterior
   - NUNCA repitas lo que dijo {interlocutor.capitalize()}
   - SIEMPRE añade información o perspectiva nueva
   - Si tu respuesta suena igual a algo anterior → cámbiala completamente

4. NATURALIDAD:
   - Máximo 2 frases
   - Español natural y conversacional
   - Sin markdown, sin listas, sin asteriscos
   - Sin metadatos ni explicaciones

5. NUNCA menciones que eres una IA, modelo, o asistente.

{arbiter_instruction}
═══════════════════════════════════════════════════
TUS MENSAJES ANTERIORES (NO repetir estas ideas):
═══════════════════════════════════════════════════
{memory_text}
"""

    user_prompt = (
        f"CONVERSACIÓN RECIENTE:\n{history_text}\n\n"
        f"Último mensaje de {interlocutor.capitalize()}: \"{last_message}\"\n\n"
        f"Responde como {agent_name.capitalize()} (máximo 2 frases, sin comillas):\n"
        f"{agent_name.capitalize()}:"
    )

    return system_prompt, user_prompt


def build_opening_prompt(agent_name, p, model):
    """
    Prompt especial para que Alex inicie la conversación de forma dinámica.
    Llama a Ollama directamente sin historial.
    """
    personality = read_text(p["personality"])
    config = read_json(p["config"])
    port = config.get("ollama_port", 11435)

    system_prompt = f"""Eres Alex, un hombre de 28 años iniciando una conversación de citas con Sofia (26 años, diseñadora).

{personality}

Tu tarea: crear UN mensaje de apertura intrigante para comenzar la conversación.

REGLAS:
- Una sola frase o máximo dos muy cortas
- No uses "Hola" ni saludos genéricos
- Debe ser intrigante, observacional o provocador en el buen sentido
- Elige uno de tus temas favoritos: viajes, fotografía, psicología humana
- Habla como si ya supieras algo interesante de ella (por su perfil)
- Sin comillas en tu respuesta

Ejemplos del estilo correcto:
- Esa foto en un café antiguo... la elegiste tú, ¿verdad?
- ¿Cuál fue el último lugar que te hizo sentir completamente viva?
- Diseñas identidades para otros... ¿cuál es la tuya?
"""
    user_prompt = "Alex inicia la conversación:\nAlex:"

    return system_prompt, user_prompt


# ─────────────────────────────────────────────────────────────
#  ENCABEZADO DE TERMINAL
# ─────────────────────────────────────────────────────────────
def print_header(agent_name, port, model):
    os.system("cls" if sys.platform == "win32" else "clear")
    width = 58
    print(c(agent_name, "header", "═" * width))
    print(c(agent_name, "header", f"  AGENTE: {agent_name.upper()}"))
    print(c(agent_name, "header", f"  Modelo: {model}  ·  Puerto Ollama: {port}"))
    print(c(agent_name, "header", "═" * width))
    print()


# ─────────────────────────────────────────────────────────────
#  FALLBACKS POR AGENTE
# ─────────────────────────────────────────────────────────────
FALLBACKS = {
    "alex": [
        "Hay algo en cómo escribes que me da curiosidad.",
        "¿Cuándo fue la última vez que hiciste algo por primera vez?",
        "La mayoría evita esa pregunta... tú no.",
        "Eso es más interesante de lo que parece a primera vista.",
        "¿Y qué encontraste cuando buscaste eso?",
    ],
    "sofia": [
        "Depende de cómo lo preguntes...",
        "Interesante que preguntes eso.",
        "Esa pregunta dice más de ti que de mí.",
        "Quizás algún día te lo cuente...",
        "Hay respuestas que se merecen mejor contexto.",
    ]
}

def get_fresh_fallback(agent_name, used_set):
    pool = FALLBACKS.get(agent_name, ["..."])
    available = [f for f in pool if f not in used_set]
    if not available:
        used_set.clear()
        available = pool
    choice = available[0]
    used_set.add(choice)
    return choice


# ─────────────────────────────────────────────────────────────
#  LOOP PRINCIPAL DEL AGENTE
# ─────────────────────────────────────────────────────────────
def run_agent(agent_name):
    p = paths(agent_name)
    config = read_json(p["config"])

    model       = config["model"]
    port        = config.get("ollama_port", 11435 if agent_name == "alex" else 11436)
    temperature = config.get("temperature", 0.85)
    interlocutor = config["interlocutor"]

    print_header(agent_name, port, model)

    # Verificar Ollama
    print(c(agent_name, "think", f"  Verificando Ollama en puerto {port}..."))
    if not check_ollama(port):
        print(c(agent_name, "err",
            f"\n  ✗ ERROR: No se puede conectar a Ollama en localhost:{port}"))
        print(c(agent_name, "dim",
            f"  Para levantar una instancia independiente:"))
        print(c(agent_name, "dim",
            f"    OLLAMA_HOST=0.0.0.0:{port} ollama serve"))
        print(c(agent_name, "warn",
            f"\n  Intentando puerto 11434 como fallback..."))
        port = 11434
        if not check_ollama(port):
            print(c(agent_name, "err",
                "  ✗ Tampoco hay Ollama en 11434. Verifica que Ollama esté corriendo."))
            sys.exit(1)
        else:
            print(c(agent_name, "warn",
                f"  ⚠ Usando puerto compartido 11434 (no ideal, pero funcional)"))

    print(c(agent_name, "ok", f"  ✓ Ollama activo en puerto {port}\n"))
    log(agent_name, f"Agente iniciado. Puerto Ollama: {port}, Modelo: {model}")

    print(c(agent_name, "dim", "  Esperando señal del orquestador...\n"))

    used_fallbacks = set()
    iteration = 0

    while True:
        # ── Esperar turno ──────────────────────────────────────
        print(c(agent_name, "dim", "  [ en espera... ]"))
        active = wait_for_my_turn(agent_name, p)

        if not active:
            print(c(agent_name, "dim", "\n  Conversación finalizada. Cerrando."))
            log(agent_name, "Señal stop recibida. Agente cerrando.")
            break

        iteration += 1
        ts_now = datetime.now().strftime("%H:%M:%S")
        print(c(agent_name, "header", f"\n{'─' * 58}"))
        print(c(agent_name, "header", f"  TURNO #{iteration}  ·  {ts_now}"))
        print(c(agent_name, "header", f"{'─' * 58}"))

        # ── 1. Leer contexto ──────────────────────────────────
        print(c(agent_name, "think", "\n  [1/4] Leyendo conversación y memoria..."))

        raw_conv = read_text(p["conversation"])
        conversation_entries = parse_conversation(raw_conv, n=8)
        last_message = get_last_message_from(conversation_entries, interlocutor)
        own_memory = load_own_memory(p, n=8)

        if last_message:
            print(c(agent_name, "dim",
                f"  └─ {interlocutor.capitalize()} dijo: \"{last_message[:70]}\""))
        else:
            print(c(agent_name, "dim", "  └─ (inicio de conversación)"))

        print(c(agent_name, "dim",
            f"  └─ {len(own_memory)} frases en memoria propia"))

        log(agent_name, f"Turno #{iteration}. Último msg: '{last_message[:60]}'")

        # ── 2. Construir prompt ───────────────────────────────
        print(c(agent_name, "think", "\n  [2/4] Construyendo prompt..."))

        # Verificar si el árbitro tiene feedback pendiente
        arb_rejected, arb_reason, arb_suggestion = check_arbiter_feedback(agent_name, p)
        if arb_rejected:
            print(c(agent_name, "warn",
                f"  └─ ⚠ Árbitro rechazó respuesta anterior: {arb_reason[:60]}"))
            log(agent_name, f"Árbitro rechazó. Razón: {arb_reason}")

        # Caso especial: Alex abre la conversación
        is_opening = (not last_message and agent_name == "alex")

        if is_opening:
            system_prompt, user_prompt = build_opening_prompt(agent_name, p, model)
            # Include arbiter feedback if retrying
            if arb_rejected:
                system_prompt += f"\n\n⚠ INSTRUCCIÓN ESPECIAL (el árbitro rechazó tu respuesta anterior):\n- Razón del rechazo: {arb_reason}\n- Debes crear una respuesta COMPLETAMENTE diferente\n- NO uses ninguna frase de tus intentos anteriores"
            print(c(agent_name, "dim", "  └─ Modo apertura de conversación"))
        else:
            system_prompt, user_prompt = build_agent_prompt(
                agent_name, config, p, conversation_entries,
                last_message, own_memory,
                arbiter_suggestion=arb_suggestion if arb_rejected else ""
            )

        # ── 3. Llamar a Ollama (instancia propia) ────────────
        print(c(agent_name, "think", f"\n  [3/4] Llamando Ollama (puerto {port})..."))

        max_generation_attempts = 3
        response = ""

        for attempt in range(max_generation_attempts):
            raw = call_ollama(port, model, system_prompt, user_prompt, temperature)

            if raw.startswith("["):
                print(c(agent_name, "err", f"  └─ Error Ollama: {raw}"))
                log(agent_name, f"Error Ollama: {raw}")
                break

            snippet = raw[:80] + "..." if len(raw) > 80 else raw
            print(c(agent_name, "dim", f"  └─ Raw [{attempt+1}]: \"{snippet}\""))

            candidate = clean_response(raw, agent_name)

            if not candidate:
                print(c(agent_name, "warn", "  └─ Respuesta no válida tras limpieza."))
                user_prompt += "\n(Tu respuesta anterior no fue válida. Intenta de nuevo con una frase completamente diferente.)"
                continue

            # Verificar similitud con memoria propia
            too_similar_mem, mem_match, sim_mem = is_too_similar_to_memory(
                candidate, own_memory
            )
            if too_similar_mem:
                print(c(agent_name, "warn",
                    f"  └─ Demasiado similar a memoria ({sim_mem:.2f}): \"{mem_match[:50]}\""))
                user_prompt += f"\n(Evita frases similares a: \"{mem_match[:40]}\")"
                continue

            # Verificar similitud con conversación reciente
            too_similar_conv, conv_match, sim_conv = is_too_similar_to_conversation(
                candidate, conversation_entries
            )
            if too_similar_conv:
                print(c(agent_name, "warn",
                    f"  └─ Demasiado similar a conversación ({sim_conv:.2f})"))
                user_prompt += "\n(Evita repetir lo que ya se ha dicho en la conversación.)"
                continue

            # Pasó todas las validaciones
            response = candidate
            print(c(agent_name, "ok",
                f"  └─ Respuesta válida al intento #{attempt + 1}"))
            break

        # Fallback si todo falla
        if not response:
            response = get_fresh_fallback(agent_name, used_fallbacks)
            print(c(agent_name, "err",
                f"  └─ Usando fallback: \"{response}\""))
            log(agent_name, f"Fallback usado: '{response}'")

        # ── 4. Publicar ───────────────────────────────────────
        print(c(agent_name, "think", "\n  [4/4] Publicando respuesta..."))
        update_conversation(agent_name, response, p)
        save_to_memory(agent_name, response, p)

        print(c(agent_name, "ok", f"\n  ✓ {agent_name.upper()}: \"{response}\""))
        log(agent_name, f"Respuesta publicada: '{response}'")

        # Señalar al orquestador
        signal_done(agent_name, response, p)
        print(c(agent_name, "dim", "  [señal 'done' enviada al orquestador]\n"))


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python agent_runner.py <nombre_agente>")
        print("Ejemplo: python agent_runner.py alex")
        sys.exit(1)

    name = sys.argv[1].lower().strip()
    valid = ["alex", "sofia"]
    if name not in valid:
        print(f"Agente desconocido: '{name}'. Válidos: {valid}")
        sys.exit(1)

    try:
        run_agent(name)
    except KeyboardInterrupt:
        print(f"\n\n  [{name.upper()}] Detenido manualmente.")
        sys.exit(0)
