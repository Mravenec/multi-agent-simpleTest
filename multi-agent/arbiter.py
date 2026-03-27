"""
arbiter.py — Árbitro Central (instancia Ollama independiente)
=============================================================
El árbitro usa su PROPIO puerto de Ollama (11434 por defecto, o el que se configure).
Evalúa cada respuesta antes de que sea aceptada en la conversación.

Si rechaza:
  1. Escribe el rechazo en shared/arbiter.json
  2. Señala al orquestador para que el agente regenere
  3. El agente recibe la sugerencia del árbitro y crea una nueva respuesta

Criterios de rechazo:
  - Respuesta de IA (menciona "asistente", "modelo", etc.)
  - Salida de personaje (habla como el otro agente)
  - Repetición exacta o casi exacta de mensajes anteriores
  - Incoherencia contextual grave
  - Longitud inválida (muy corta o muy larga)

Puerto por defecto: 11434 (árbitro neutral)
"""

import os
import sys
import json
import time
import re
import urllib.request
from datetime import datetime


# ─────────────────────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ARBITER_CONFIG = {
    "model": "qwen2.5:1.5b",
    "port": 11434,            # Puerto dedicado al árbitro
    "temperature": 0.3,       # Baja temperatura → más consistente y severo
    "max_tokens": 100,
}

PATHS = {
    "arbiter":      os.path.join(BASE_DIR, "shared", "arbiter.json"),
    "signal":       os.path.join(BASE_DIR, "shared", "signal.json"),
    "conversation": os.path.join(BASE_DIR, "shared", "conversation.txt"),
    "log":          os.path.join(BASE_DIR, "logs", "arbiter.log"),
}


# ─────────────────────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────────────────────
def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def log_arb(message):
    os.makedirs(os.path.dirname(PATHS["log"]), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(PATHS["log"], "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")

def ts():
    return datetime.now().strftime("%H:%M:%S")


# ─────────────────────────────────────────────────────────────
#  REGLAS RÁPIDAS (sin llamar a Ollama) — primera línea de defensa
# ─────────────────────────────────────────────────────────────

# Frases que delatan respuestas de IA o fuera de personaje
HARD_REJECT_PHRASES = [
    "como asistente", "como ia", "soy una ia", "soy un modelo",
    "modelo de lenguaje", "inteligencia artificial",
    "estoy aquí para ayudar", "puedo ayudarte",
    "lo siento mucho por el malentendido",
    "aprecio tu preocupación",
    "gracias por entenderlo",
    "estaré encantad",
    "no puedo continuar esta conversación",
    "no puedo decir", "podría dañar la confianza",
    "qwen", "llama", "assistant",
]

def quick_reject(response_text, agent_name):
    """
    Rechazos rápidos basados en reglas sin llamar a Ollama.
    Retorna (rejected: bool, reason: str)
    """
    text_lower = response_text.lower()

    # Muy corta o muy larga
    if len(response_text.strip()) < 8:
        return True, "Respuesta demasiado corta (menos de 8 caracteres)"
    if len(response_text.strip()) > 500:
        return True, "Respuesta demasiado larga (más de 500 caracteres)"

    # Frases de IA
    for phrase in HARD_REJECT_PHRASES:
        if phrase in text_lower:
            return True, f"Contiene frase de IA/asistente: '{phrase}'"

    # Habla como el otro agente
    other = "sofia" if agent_name == "alex" else "alex"
    if re.search(rf'\bsoy\s+{other}\b', text_lower):
        return True, f"El agente se identifica como {other}"

    # Repetición exacta (idéntica a sí misma — loops)
    lines = [l.strip() for l in response_text.split("\n") if l.strip()]
    if len(lines) >= 2:
        unique = set(l.lower() for l in lines)
        if len(unique) < len(lines) * 0.6:
            return True, "Respuesta con líneas repetidas internamente"

    return False, ""


def jaccard_similarity(s1, s2):
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    if not set1 or not set2:
        return 0.0
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union > 0 else 0.0

def repetition_reject(response_text, recent_messages):
    """
    Verifica si la respuesta es demasiado similar a mensajes recientes.
    Retorna (rejected: bool, reason: str)
    """
    for msg in recent_messages:
        sim = jaccard_similarity(response_text, msg)
        if sim > 0.6:
            return True, f"Repite mensaje anterior (similitud {sim:.2f}): '{msg[:50]}'"
    return False, ""


# ─────────────────────────────────────────────────────────────
#  EVALUACIÓN CON OLLAMA (árbitro inteligente)
# ─────────────────────────────────────────────────────────────
def call_arbiter_ollama(response_text, agent_name, interlocutor,
                        last_message, conversation_context):
    """
    Usa el Ollama del árbitro para evaluar si la respuesta es coherente
    con el personaje y la conversación.
    """
    port = ARBITER_CONFIG["port"]
    model = ARBITER_CONFIG["model"]
    temperature = ARBITER_CONFIG["temperature"]

    system_prompt = """Eres un árbitro de calidad conversacional. Tu trabajo es evaluar
si una respuesta en una conversación de citas es apropiada.

CRITERIOS ESTRICTOS DE RECHAZO (rechaza si NO cumple cualquiera):
1. ¿La respuesta RESPONDE DIRECTAMENTE al último mensaje del interlocutor? (no cambia de tema, no ignora la pregunta/comentario)
2. ¿La respuesta está en español natural? (no inglés, no broken Spanish)
3. ¿La respuesta suena humana y natural? (no como un chatbot o asistente)
4. ¿No repite exactamente frases o ideas de mensajes anteriores?
5. ¿Es coherente con el contexto de la conversación? (no salta a temas no relacionados)
6. ¿La respuesta es relevante y continúa la conversación? (no tangentes irrelevantes)
7. ¿La respuesta es CONCRETA y tiene significado real? (no frases abstractas o pseudo-poéticas sin referente claro)
8. ¿NO inventa lugares, eventos o contextos no mencionados? (no alucinaciones contextuales)
9. ¿NO contiene meta-mensajes? (no habla como sistema/IA, no describe personalidad fuera del rol)
10. ¿La respuesta añade algo nuevo o profundiza la conversación? (no ecos semánticos o reformulaciones vacías)

RECHAZA SIEMPRE que la respuesta no responda directamente al mensaje recibido, invente contexto, sea abstracta sin sentido, o rompa el personaje.

RESPONDE SOLO con este formato JSON (sin markdown, sin texto adicional):
{"verdict": "accept", "reason": "explicación breve"}
o
{"verdict": "reject", "reason": "razón específica del rechazo", "suggestion": "qué debería hacer en su lugar"}"""

    user_prompt = f"""AGENTE: {agent_name.capitalize()}
CONVERSACIÓN RECIENTE:
{conversation_context}

ÚLTIMO MENSAJE RECIBIDO DE {interlocutor.upper()}:
"{last_message}"

RESPUESTA PROPUESTA DE {agent_name.upper()}:
"{response_text}"

¿Debes aceptar o rechazar esta respuesta? Responde SOLO en JSON:"""

    url = f"http://localhost:{port}/api/generate"
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 120,
            "stop": ["\n\n", "```"]
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                result = json.loads(resp.read().decode("utf-8"))
                raw = result.get("response", "").strip()
                # Intentar parsear JSON de respuesta
                try:
                    # Extraer JSON aunque haya texto extra
                    json_match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                except Exception:
                    pass
    except Exception as e:
        log_arb(f"Error llamando Ollama árbitro: {e}")

    # Si falla, aceptar por defecto (no bloquear por error del árbitro)
    return {"verdict": "accept", "reason": "árbitro no disponible, aprobado por defecto"}


# ─────────────────────────────────────────────────────────────
#  EVALUACIÓN COMPLETA
# ─────────────────────────────────────────────────────────────
def evaluate_response(response_text, agent_name, interlocutor,
                      last_message, conversation_entries):
    """
    Pipeline completo de evaluación:
    1. Reglas rápidas (sin Ollama)
    2. Verificación de repetición
    3. Evaluación semántica con Ollama (árbitro)
    """

    # Paso 1: Reglas rápidas
    rejected, reason = quick_reject(response_text, agent_name)
    if rejected:
        log_arb(f"RECHAZO RÁPIDO [{agent_name}]: {reason}")
        return {
            "verdict": "reject",
            "reason": reason,
            "suggestion": "Responde de forma natural como tu personaje, sin frases de IA",
            "method": "quick_rules"
        }

    # Paso 2: Verificar repetición
    recent_msgs = [e["message"] for e in conversation_entries[-6:]]
    rejected, reason = repetition_reject(response_text, recent_msgs)
    if rejected:
        log_arb(f"RECHAZO REPETICIÓN [{agent_name}]: {reason}")
        return {
            "verdict": "reject",
            "reason": reason,
            "suggestion": "Crea una respuesta completamente nueva con ideas diferentes",
            "method": "repetition_check"
        }

    # Paso 3: Evaluación con Ollama si está disponible
    context_lines = [f"{e['agent'].capitalize()}: {e['message']}"
                     for e in conversation_entries[-4:]]
    conversation_context = "\n".join(context_lines) if context_lines else "(inicio)"

    ollama_result = call_arbiter_ollama(
        response_text, agent_name, interlocutor,
        last_message, conversation_context
    )

    verdict = ollama_result.get("verdict", "accept")
    reason = ollama_result.get("reason", "")
    suggestion = ollama_result.get("suggestion", "")

    if verdict == "reject":
        log_arb(f"RECHAZO OLLAMA [{agent_name}]: {reason} | Sugerencia: {suggestion}")
    else:
        log_arb(f"APROBADO [{agent_name}]: {reason}")

    return {
        "verdict": verdict,
        "reason": reason,
        "suggestion": suggestion,
        "method": "ollama_arbiter"
    }


# ─────────────────────────────────────────────────────────────
#  API PÚBLICA DEL ÁRBITRO
# ─────────────────────────────────────────────────────────────
def parse_conversation_for_arbiter(raw_text, n=8):
    """Parsea la conversación para uso del árbitro."""
    entries = []
    blocks = re.split(r'\n(?=\[\d{2}:\d{2}:\d{2}\])', raw_text)
    for block in blocks:
        m = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s+(ALEX|SOFIA):\s*\n?(.*)',
                     block.strip(), re.DOTALL)
        if m:
            t, agent, msg = m.groups()
            msg_lines = [l.strip() for l in msg.strip().split("\n") if l.strip()]
            msg_clean = msg_lines[0].strip('"').strip("'").strip() if msg_lines else ""
            if msg_clean and len(msg_clean) > 3:
                entries.append({
                    "time": t,
                    "agent": agent.lower(),
                    "message": msg_clean
                })
    return entries[-n:]

def write_arbiter_result(agent_name, result):
    """Escribe el resultado del árbitro en shared/arbiter.json."""
    write_json(PATHS["arbiter"], {
        "target_agent": agent_name,
        "verdict": result["verdict"],
        "reason": result["reason"],
        "suggestion": result.get("suggestion", ""),
        "method": result.get("method", ""),
        "timestamp": datetime.now().isoformat()
    })

def clear_arbiter():
    """Limpia el archivo del árbitro (sin veredito pendiente)."""
    write_json(PATHS["arbiter"], {
        "target_agent": "",
        "verdict": "none",
        "reason": "",
        "suggestion": "",
        "timestamp": datetime.now().isoformat()
    })

def arbiter_check(agent_name, response_text):
    """
    Función principal llamada por el orquestador para validar una respuesta.
    
    Retorna:
        True  → respuesta aceptada
        False → respuesta rechazada (detalles en shared/arbiter.json)
    """
    config_agents = {
        "alex": "sofia",
        "sofia": "alex"
    }
    interlocutor = config_agents.get(agent_name, "")

    # Leer conversación actual
    try:
        raw_conv = open(PATHS["conversation"], "r", encoding="utf-8").read()
        conv_entries = parse_conversation_for_arbiter(raw_conv, n=8)
    except Exception:
        conv_entries = []

    # Obtener último mensaje del interlocutor
    last_msg = ""
    for entry in reversed(conv_entries):
        if entry["agent"] == interlocutor:
            last_msg = entry["message"]
            break

    # Evaluar
    result = evaluate_response(
        response_text, agent_name, interlocutor,
        last_msg, conv_entries
    )

    write_arbiter_result(agent_name, result)

    accepted = result["verdict"] == "accept"
    status = "✓ ACEPTADO" if accepted else "✗ RECHAZADO"
    print(f"  [Árbitro] {status} ({result.get('method', 'N/A')}): {result['reason'][:70]}")

    return accepted
