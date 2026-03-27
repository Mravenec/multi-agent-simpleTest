"""
agent_runner.py — Terminal de Agente
Uso: python agent_runner.py <nombre_agente>
Ejemplo: python agent_runner.py alex
"""

import sys
import os
import json
import time
import re
import urllib.request
import urllib.error
from datetime import datetime

# ─────────────────────────────────────────────
#  COLORES (cross-platform via ANSI)
# ─────────────────────────────────────────────
def supports_color():
    """Detecta si la terminal soporta colores ANSI."""
    if sys.platform == "win32":
        # Windows 10+ con VT processing habilitado
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

USE_COLOR = supports_color()

COLORS = {
    "alex": {
        "header": "\033[94m",   # Azul
        "think":  "\033[96m",   # Cyan
        "speak":  "\033[97m",   # Blanco brillante
        "dim":    "\033[90m",   # Gris
        "ok":     "\033[92m",   # Verde
        "err":    "\033[91m",   # Rojo
        "reset":  "\033[0m",
    },
    "sofia": {
        "header": "\033[95m",   # Magenta
        "think":  "\033[93m",   # Amarillo
        "speak":  "\033[97m",   # Blanco brillante
        "dim":    "\033[90m",   # Gris
        "ok":     "\033[92m",   # Verde
        "err":    "\033[91m",   # Rojo
        "reset":  "\033[0m",
    },
}

def c(agent, key, text):
    """Aplica color si el terminal lo soporta."""
    if not USE_COLOR:
        return text
    palette = COLORS.get(agent, COLORS["alex"])
    return f"{palette[key]}{text}{palette['reset']}"


# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Adjust if running from subfolder (e.g., agents/alex/)
while not os.path.exists(os.path.join(BASE_DIR, "shared")) and BASE_DIR != os.path.dirname(BASE_DIR):
    BASE_DIR = os.path.dirname(BASE_DIR)

def paths(agent_name):
    return {
        "config":       os.path.join(BASE_DIR, "agents", agent_name, "config.json"),
        "personality":  os.path.join(BASE_DIR, "agents", agent_name, "personality.md"),
        "memory":       os.path.join(BASE_DIR, "agents", agent_name, "memory.md"),
        "conversation": os.path.join(BASE_DIR, "shared", "conversation.txt"),
        "state":        os.path.join(BASE_DIR, "shared", "state.json"),
        "signal":       os.path.join(BASE_DIR, "shared", "signal.json"),
        "log":          os.path.join(BASE_DIR, "logs", f"{agent_name}.log"),
    }


# ─────────────────────────────────────────────
#  UTILIDADES PARA MEMORIA
# ─────────────────────────────────────────────
def is_similar_to_memory(response, memory_list):
    """Verifica si la respuesta es demasiado similar a frases recientes en memoria."""
    response_lower = response.lower()
    for mem in memory_list:
        mem_lower = mem.lower()
        if mem_lower in response_lower and len(mem) > 10:  # Evitar falsos positivos con palabras cortas
            return True
    return False

def is_fallback_used(fallback, memory_list):
    """Check if fallback was recently used in memory."""
    fallback_lower = fallback.lower().strip()
    for mem in memory_list[-10:]:  # Check last 10 memory entries
        if fallback_lower in mem.lower():
            return True
    return False

def is_duplicate_in_conversation(response, conversation_entries, agent_name, threshold=0.5):
    """Check if response is too similar to recent conversation messages."""
    response_lower = response.lower().strip()
    for entry in conversation_entries[-5:]:  # Last 5 messages
        if entry["agent"] == agent_name:  # Skip own messages
            continue
        msg_lower = entry["message"].lower().strip()
        # Simple similarity: check if 70% of words overlap
        words_resp = set(response_lower.split())
        words_msg = set(msg_lower.split())
        if words_resp and words_msg:
            intersection = words_resp & words_msg
            union = words_resp | words_msg
            similarity = len(intersection) / len(union)
            if similarity > threshold:
                return True
    return False
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
    """Escribe en el log del agente."""
    p = paths(agent_name)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}\n"
    os.makedirs(os.path.dirname(p["log"]), exist_ok=True)
    append_text(p["log"], line)


# ─────────────────────────────────────────────
#  LEER SEÑAL DEL ORQUESTADOR
# ─────────────────────────────────────────────
def wait_for_signal(agent_name, p):
    """
    Espera activamente hasta que el orquestador señale este agente.
    Retorna True cuando es su turno, False si la conversación terminó.
    """
    while True:
        try:
            sig = read_json(p["signal"])
        except Exception:
            time.sleep(0.3)
            continue

        if sig.get("signal") == "stop":
            return False

        if sig.get("signal") == "go" and sig.get("target_agent") == agent_name:
            return True

        time.sleep(0.4)


# ─────────────────────────────────────────────
#  CONSTRUIR CONVERSACIÓN RECIENTE
# ─────────────────────────────────────────────
def parse_conversation(raw_text, n=6):
    """
    Extrae los últimos n mensajes del archivo de conversación.
    Formato en archivo: [HH:MM:SS] AGENT:\nmensaje
    Retorna lista de dicts: {agent, message, time}
    """
    entries = []
    blocks = re.split(r'\n(?=\[\d{2}:\d{2}:\d{2}\])', raw_text)
    for block in blocks:
        block = block.strip()
        match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s+(ALEX|SOFIA):\s*\n?(.*)', block, re.DOTALL)
        if match:
            t, agent, msg = match.groups()
            msg = msg.strip().split("\n")[0].strip()  # Solo primera línea del mensaje
            if msg:
                entries.append({"time": t, "agent": agent.lower(), "message": msg})
    return entries[-n:]


def get_last_message(conversation_entries, interlocutor):
    """Obtiene el último mensaje del interlocutor."""
    for entry in reversed(conversation_entries):
        if entry["agent"] == interlocutor:
            return entry["message"]
    return ""


def check_ollama_server():
    """Check if Ollama server is running and accessible."""
    url = "http://localhost:11434/api/tags"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# ─────────────────────────────────────────────
#  LLAMADA A OLLAMA
# ─────────────────────────────────────────────
def call_ollama(model, system_prompt, user_prompt, temperature=0.8):
    if not check_ollama_server():
        return "Error: Ollama server not running or accessible"
    
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "top_k": 30,
            "num_predict": 300,
            "stop": ["Alex:", "Sofia:", "ALEX:", "SOFIA:", "assistant:", "User:"]
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status == 200:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
            return f"Error HTTP: {resp.status}"
    except Exception as e:
        return f"Error: {e}"


# ─────────────────────────────────────────────
#  LIMPIAR RESPUESTA
# ─────────────────────────────────────────────
FORBIDDEN_PATTERNS = [
    "hola", "¿cómo estás", "cómo estas", "buenos días", "buen día",
    "como asistente", "modelo de lenguaje", "soy una ia", "soy un ia",
    "inteligencia artificial", "qwen", "assist you", "eres muy guapa",
    "¿a qué te dedicas", "que tal", "¿qué tal",
    # New: narration patterns
    "confieso", "digo", "susurro", "pienso", "siento", "guiñándome", "sonriendo", "riendo",
    "me guiño", "me sonrío", "me río", "me río", "me río", "me río", # variations
    # Pronouns breaking immersion
    "yo ", "me ", "mi ", "mí ", # only if not natural
    # Repetition markers
    "...", "uhm", "ehm",
]

def clean_response(raw, agent_name):
    """Limpia metadatos, formatos markdown y patrones prohibidos."""
    text = raw

    # Eliminar secciones markdown completas
    text = re.sub(r'#{1,3}.*', '', text, flags=re.DOTALL)
    text = re.sub(r'\*\*.*?\*\*', '', text, flags=re.DOTALL)
    text = re.sub(r'- \w.*', '', text, flags=re.DOTALL)
    text = re.sub(r'\[.*?\]', '', text, flags=re.DOTALL)

    # Limpiar secciones de personalidad que el modelo puede filtrar
    sections = [
        "Tono:", "Ritmo:", "Temas favoritos:", "Evito:", "PROHIBIDO",
        "Fondo Personal", "Esencia", "Deseos", "Miedos", "Estilo",
        "Voz de Ejemplo", "Señales", "Perfil:", "personality"
    ]
    for s in sections:
        text = re.sub(rf'{re.escape(s)}.*', '', text, flags=re.DOTALL)

    # Limpiar timestamps residuales
    text = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', text)
    text = re.sub(r'\[\d{4}-\d{2}-\d{2}.*?\]', '', text, flags=re.DOTALL)

    # Normalizar espacios
    text = re.sub(r'\s+', ' ', text).strip()

    # Permitir respuestas multi-línea y párrafos
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return ""
    text = "\n".join(lines)  # Mantener párrafos separados por líneas

    # Enforce single line for Alex per personality
    if agent_name == "alex" and "\n" in text:
        text = text.split("\n")[0]

    # Filtro de patrones prohibidos
    text_lower = text.lower()
    for pat in FORBIDDEN_PATTERNS:
        if pat in text_lower:
            return ""

    # Filtro de auto-referencia con nombre propio
    if re.search(rf'\bsoy\s+{agent_name}\b', text_lower):
        return ""

    # Validar longitud (relajada para párrafos)
    if len(text) < 5 or len(text) > 1000:
        return ""

    return text


# ─────────────────────────────────────────────
#  CONSTRUIR PROMPT
# ─────────────────────────────────────────────
def build_prompt(agent_name, config, p, conversation_entries, last_message):
    personality = read_text(p["personality"])
    memory_raw = read_text(p["memory"])
    interlocutor = config["interlocutor"]

    # Memoria: últimas 5 respuestas propias (sin timestamps ni headers)
    memory_lines = [
        l.strip() for l in memory_raw.split("\n")
        if l.strip() and not l.startswith("#") and not l.startswith("[")
    ]
    memory_text = "\n".join(memory_lines[-5:])

    # Historial reciente formateado
    history_text = ""
    for entry in conversation_entries[-4:]:
        speaker = entry["agent"].capitalize()
        history_text += f"{speaker}: {entry['message']}\n"

    system_prompt = f"""You are a conversational AI agent participating in a 1-to-1 dialogue.

STRICT RULES (MANDATORY):

IDENTITY:
- You are ONLY {agent_name}.
- You are speaking to {interlocutor}.
- NEVER speak as the other agent.
- NEVER narrate actions (no "I said", "she smiled", etc).

RESPONSE REQUIREMENTS:
- Your response MUST directly address the last message from {interlocutor}.
- If the last message is a question, ANSWER IT FIRST.
- Add new information or ask a related question to continue the conversation.
- Keep responses natural and conversational.

CRITICAL BEHAVIOR RULES:
1. NEVER repeat sentences or phrases from the conversation history.
2. NEVER copy or paraphrase the other agent's message.
3. ALWAYS add new value to the conversation.
4. NEVER jump to unrelated topics without transition.
5. Stay in character as defined in your personality.

MEMORY RULES:
- DO NOT invent shared past experiences.
- DO NOT assume events happened unless explicitly stated.
- DO NOT create fake memories.

LANGUAGE RULES:
- Use natural, fluent Spanish.
- Avoid strange metaphors or nonsensical phrases.
- Avoid poetic overgeneration.
- No roleplay narration.

FORBIDDEN:
- Repeating the same prompt
- Echoing previous messages
- Acting as narrator
- Switching roles
- Copying text blocks
- Using phrases like "confieso", "digo", "susurro", "pienso", "siento"
- Self-referential narration like "guiñándome el ojo"

OUTPUT FORMAT:
- Plain text only
- One coherent message
- No quotes unless necessary
- No markdown

GOAL:
Maintain a coherent, realistic conversation where each reply advances the dialogue naturally.

{personality}

TU MEMORIA RECIENTE (NO repitas estas frases exactas, varía tu lenguaje):
{memory_text}
"""

    user_prompt = (
        f"MENSAJE A RESPONDER de {interlocutor.capitalize()}: {last_message}\n\n"
        f"CONTEXTO DE LA CONVERSACIÓN RECIENTE (solo para referencia, no repitas):\n{history_text}\n"
        f"{agent_name.capitalize()}:"
    )

    return system_prompt, user_prompt


# ─────────────────────────────────────────────
#  ACTUALIZAR MEMORIA
# ─────────────────────────────────────────────
def update_memory(agent_name, response, p):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    append_text(p["memory"], f"\n[{ts}] {response}")


# ─────────────────────────────────────────────
#  ACTUALIZAR CONVERSACIÓN COMPARTIDA
# ─────────────────────────────────────────────
def update_conversation(agent_name, response, p):
    ts = datetime.now().strftime("%H:%M:%S")
    append_text(p["conversation"], f"\n\n[{ts}] {agent_name.upper()}:\n{response}\n")


# ─────────────────────────────────────────────
#  SEÑALAR LISTO AL ORQUESTADOR
# ─────────────────────────────────────────────
def signal_done(agent_name, p):
    sig = {
        "signal": "done",
        "target_agent": agent_name,
        "timestamp": datetime.now().isoformat()
    }
    write_json(p["signal"], sig)


# ─────────────────────────────────────────────
#  ENCABEZADO DE TERMINAL
# ─────────────────────────────────────────────
def print_header(agent_name):
    p = paths(agent_name)
    personality_raw = read_text(p["personality"])
    # Extract first few lines with actual content
    lines = [l.strip() for l in personality_raw.split("\n") if l.strip() and not l.startswith("#")]
    personality_summary = " ".join(lines[:3])  # First 3 content lines
    personality_summary = personality_summary[:100] + "..." if len(personality_summary) > 100 else personality_summary

    os.system("cls" if sys.platform == "win32" else "clear")
    width = 55
    name = agent_name.upper()
    print(c(agent_name, "header", "═" * width))
    print(c(agent_name, "header", f"  AGENTE: {name}"))
    print(c(agent_name, "header", "═" * width))
    print(c(agent_name, "dim", f"  Personalidad: {personality_summary}"))
    print()


# ─────────────────────────────────────────────
#  LOOP PRINCIPAL DEL AGENTE
# ─────────────────────────────────────────────
def run_agent(agent_name):
    p = paths(agent_name)
    config = read_json(p["config"])
    interlocutor = config["interlocutor"]
    model = config["model"]
    temperature = config.get("temperature", 0.9)

    print_header(agent_name)
    print(c(agent_name, "dim", f"  Modelo: {model}"))
    print(c(agent_name, "dim", f"  Esperando turno del orquestador...\n"))
    log(agent_name, "Agente iniciado.")

    fallback_pool = {
        "alex":  [
            "Tu perfil dice que coleccionas momentos... cuéntame uno.",
            "¿Qué parte de tu día merece ser fotografiada hoy?",
            "Algo en cómo escribes me hace querer saber más.",
            "¿Cuál ha sido tu viaje más memorable hasta ahora?",
            "Si pudieras capturar un instante perfecto, ¿cuál sería?",
            "¿Qué te inspira cuando observas a la gente?",
            "¿Cuál es el libro que más te ha marcado?",
            "¿Qué lugar del mundo te hace sentir más viva?",
            "¿Qué aspecto de la tecnología te fascina más?",
            "¿Cómo describes tu estilo de comunicación?"
        ],
        "sofia": [
            "Depende de cómo lo preguntes...",
            "Eso es lo que querías escuchar, ¿verdad?",
            "Interesante que preguntes eso...",
            "¿Y si te dijera que depende del contexto?",
            "Quizás, pero prefiero no generalizar.",
            "¿Qué te hace pensar que necesito explicarlo?",
            "Eso suena como una pregunta profunda...",
            "¿Por qué te importa tanto ese detalle?",
            "Digamos que la respuesta no es tan simple.",
            "¿Quieres que sea sincera o diplomática?"
        ]
    }
    used_fallbacks = set()

    iteration = 0

    while True:
        # ── Esperar señal del orquestador ──
        print(c(agent_name, "dim", "  [esperando señal...]"))
        active = wait_for_signal(agent_name, p)
        if not active:
            print(c(agent_name, "dim", "\n  Conversación finalizada. Cerrando agente."))
            log(agent_name, "Señal de stop recibida.")
            break

        iteration += 1
        ts_now = datetime.now().strftime("%H:%M:%S")
        print(c(agent_name, "header", f"\n{'─'*55}"))
        print(c(agent_name, "header", f"  TURNO #{iteration}  ·  {ts_now}"))
        print(c(agent_name, "header", f"{'─'*55}"))

        # ── 1. Leer contexto ──
        print(c(agent_name, "think", "\n  [1/4] Leyendo conversación..."))
        raw_conv = read_text(p["conversation"])
        conversation_entries = parse_conversation(raw_conv, n=6)
        last_message = get_last_message(conversation_entries, interlocutor)

        if last_message:
            print(c(agent_name, "dim", f"  └─ {interlocutor.capitalize()} dijo: \"{last_message}\""))
        else:
            print(c(agent_name, "dim", f"  └─ (inicio de conversación)"))

        log(agent_name, f"Turno #{iteration}. Último mensaje: '{last_message}'")

        # ── 2. Pensar / analizar ──
        print(c(agent_name, "think", "\n  [2/4] Analizando y construyendo prompt..."))
        time.sleep(0.3)  # Simula pensamiento visible

        if not last_message and agent_name == "alex":
            # Alex inicia la conversación - generate dynamic starting message
            personality = read_text(p["personality"])
            system_prompt = f"""Eres {agent_name.capitalize()}, un hombre de 28 años. Estás iniciando una conversación de citas con Sofia, una mujer de 26 años.

{personality}

REGLAS PARA EL INICIO:
- Eres un hombre directo, observador y analítico
- Inicia con algo intrigante y personal, no genérico
- Mantén tu tono seguro con toques de sarcasmo inteligente
- Elige un tema de tus intereses: viajes, fotografía, tecnología, psicología humana
- NO uses saludos como "Hola" o "¿Cómo estás?"
- Responde con una sola frase intrigante y corta

Ejemplos de inicio:
- "Esa foto en tu perfil tiene historia... puedo verlo en tus ojos."
- "Viajas mucho, ¿cuál fue el último lugar que te hizo sentir viva?"
- "¿Cuál fue el libro que cambió tu perspectiva sobre el mundo?"

Responde SOLO con tu mensaje de inicio:"""

            user_prompt = f"{agent_name.capitalize()}, inicia la conversación con Sofia:"
            raw_response = call_ollama(model, system_prompt, user_prompt, temperature)
            response = clean_response(raw_response, agent_name)
            if not response:
                # Fallback if generation fails
                response = "Viajas mucho, ¿cuál fue el último lugar que te hizo sentir viva?"
            print(c(agent_name, "dim", "  └─ Iniciando conversación dinámicamente."))
            memory_lines = []  # No hay memoria previa para el inicio
        else:
            system_prompt, user_prompt = build_prompt(
                agent_name, config, p, conversation_entries, last_message
            )

            # Leer memoria para verificar similitud
            memory_raw = read_text(p["memory"])
            memory_lines = [
                l.strip() for l in memory_raw.split("\n")
                if l.strip() and not l.startswith("#") and not l.startswith("[")
            ]

            # ── 3. Llamar a Ollama ──
            print(c(agent_name, "think", "\n  [3/4] Generando respuesta con Ollama..."))
            raw_response = call_ollama(model, system_prompt, user_prompt, temperature)
            print(c(agent_name, "dim", f"  └─ Raw: \"{raw_response[:80]}...\"" if len(raw_response) > 80 else f"  └─ Raw: \"{raw_response}\""))

            # Verificar similitud con memoria reciente
            if is_similar_to_memory(raw_response, memory_lines[-5:]):
                print(c(agent_name, "err", "  └─ Respuesta demasiado similar a memoria reciente, intentando de nuevo..."))
                # Intentar una vez más con prompt ajustado
                user_prompt_retry = user_prompt + "\nIMPORTANTE: Crea una respuesta completamente nueva, no uses frases similares a las anteriores."
                raw_response = call_ollama(model, system_prompt, user_prompt_retry, temperature)
                print(c(agent_name, "dim", f"  └─ Reintento: \"{raw_response[:80]}...\"" if len(raw_response) > 80 else f"  └─ Reintento: \"{raw_response}\""))
                if is_similar_to_memory(raw_response, memory_lines[-5:]):
                    raw_response = ""  # Forzar fallback

            response = clean_response(raw_response, agent_name)

            # Additional duplicate check against conversation
            if is_duplicate_in_conversation(response, conversation_entries, agent_name, threshold=0.5):
                print(c(agent_name, "err", "  └─ Respuesta demasiado similar a conversación reciente, intentando de nuevo..."))
                # Force fallback
                response = ""

            if not response:
                # Fallback inteligente: no repetir
                pool = fallback_pool.get(agent_name, ["..."])
                available = [f for f in pool if f not in used_fallbacks and not is_fallback_used(f, memory_lines)]
                if not available:
                    used_fallbacks.clear()
                    available = [f for f in pool if not is_fallback_used(f, memory_lines)]
                    if not available:
                        available = pool  # Last resort
                response = available[0]
                used_fallbacks.add(response)
                print(c(agent_name, "err", f"  └─ Respuesta inválida, usando fallback."))
                log(agent_name, f"Fallback usado: '{response}'")

        # ── 4. Publicar respuesta ──
        print(c(agent_name, "think", "\n  [4/4] Publicando respuesta..."))
        update_conversation(agent_name, response, p)
        update_memory(agent_name, response, p)

        print(c(agent_name, "ok", f"\n  ✓ {agent_name.upper()}: \"{response}\""))
        log(agent_name, f"Respuesta: '{response}'")

        # ── Señalar al orquestador que terminó ──
        signal_done(agent_name, p)
        print(c(agent_name, "dim", "\n  [señal enviada al orquestador]"))


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python agent_runner.py <nombre_agente>")
        print("Ejemplo: python agent_runner.py alex")
        sys.exit(1)

    agent_name = sys.argv[1].lower().strip()
    valid_agents = ["alex", "sofia"]

    if agent_name not in valid_agents:
        print(f"Agente desconocido: '{agent_name}'. Válidos: {valid_agents}")
        sys.exit(1)

    try:
        run_agent(agent_name)
    except KeyboardInterrupt:
        print(f"\n\n  [{agent_name.upper()}] Detenido manualmente.")
        sys.exit(0)
