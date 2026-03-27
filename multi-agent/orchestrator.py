"""
orchestrator.py — Orquestador Central con Árbitro Integrado
============================================================

Arquitectura de 3 instancias Ollama independientes:

  Puerto 11434 → Árbitro  (evalúa respuestas, qwen2.5:1.5b, temp=0.3)
  Puerto 11435 → Alex     (genera respuestas, qwen2.5:1.5b, temp=0.85)
  Puerto 11436 → Sofia    (genera respuestas, qwen2.5:1.5b, temp=0.90)

Flujo por turno:
  1. Orquestador señala al agente → go
  2. Agente genera respuesta con su Ollama privado
  3. Agente señala done con su respuesta
  4. Orquestador pasa respuesta al Árbitro
  5a. Árbitro acepta → escribe en conversación, pasa al siguiente agente
  5b. Árbitro rechaza → devuelve al mismo agente con sugerencia (máx 2 reintentos)

Uso:
    python orchestrator.py
"""

import os
import sys
import json
import time
import subprocess
import platform
from datetime import datetime

# ─────────────────────────────────────────────────────────────
#  COLORES
# ─────────────────────────────────────────────────────────────
def enable_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass

enable_ansi()

R    = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"

C_GOLD  = "\033[38;5;220m"
C_WHITE = "\033[38;5;250m"
C_ORG   = "\033[38;5;214m"
C_GREEN = "\033[38;5;82m"
C_RED   = "\033[38;5;196m"
C_GRAY  = "\033[38;5;240m"
C_ALEX  = "\033[38;5;75m"
C_SOFIA = "\033[38;5;213m"
C_ARB   = "\033[38;5;226m"

def ca(name, text):
    col = C_ALEX if name == "alex" else (C_SOFIA if name == "sofia" else C_ARB)
    return f"{col}{text}{R}"

# ─────────────────────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SIGNAL_PATH = os.path.join(BASE_DIR, "shared", "signal.json")
STATE_PATH  = os.path.join(BASE_DIR, "shared", "state.json")
CONV_PATH   = os.path.join(BASE_DIR, "shared", "conversation.txt")
ARBITER_PATH= os.path.join(BASE_DIR, "shared", "arbiter.json")
LOG_PATH    = os.path.join(BASE_DIR, "logs", "orchestrator.log")
AGENT_SCRIPT= os.path.join(BASE_DIR, "agent_runner.py")

# ─────────────────────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────────────────────
def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def log_orc(message):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")

def clear():
    os.system("cls" if sys.platform == "win32" else "clear")

def ts():
    return datetime.now().strftime("%H:%M:%S")

def append_text(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)

def update_conversation(agent_name, response, conv_path):
    """Escribe la respuesta del agente al archivo compartido de conversación."""
    ts = datetime.now().strftime("%H:%M:%S")
    append_text(conv_path, f"\n\n[{ts}] {agent_name.upper()}:\n{response}\n")


# ─────────────────────────────────────────────────────────────
#  ÁRBITRO — LLAMADO DIRECTO (sin subprocess)
# ─────────────────────────────────────────────────────────────
def run_arbiter(agent_name, response_text):
    """
    Importa y llama al árbitro directamente en el mismo proceso.
    Esto evita overhead de subprocess y mantiene contexto compartido.
    """
    try:
        # Import dinámico para evitar problemas de módulo al inicio
        import importlib.util
        arbiter_path = os.path.join(BASE_DIR, "arbiter.py")
        spec = importlib.util.spec_from_file_location("arbiter", arbiter_path)
        arb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(arb)
        return arb.arbiter_check(agent_name, response_text)
    except Exception as e:
        print(f"{C_RED}  [Árbitro] Error: {e}{R}")
        log_orc(f"Error árbitro: {e}")
        # Si el árbitro falla, aprobar por defecto para no bloquear la conversación
        return True


# ─────────────────────────────────────────────────────────────
#  SEÑALES
# ─────────────────────────────────────────────────────────────
def signal_go(agent_name):
    write_json(SIGNAL_PATH, {
        "signal": "go",
        "target_agent": agent_name,
        "timestamp": datetime.now().isoformat()
    })

def signal_retry(agent_name):
    """Señal especial: el árbitro rechazó, el agente debe reintentar."""
    write_json(SIGNAL_PATH, {
        "signal": "go",          # Mismo 'go', el agente lee arbiter.json
        "target_agent": agent_name,
        "is_retry": True,
        "timestamp": datetime.now().isoformat()
    })

def signal_stop():
    write_json(SIGNAL_PATH, {
        "signal": "stop",
        "target_agent": "",
        "timestamp": datetime.now().isoformat()
    })

def clear_arbiter_state():
    """Limpia el estado del árbitro entre turnos."""
    write_json(ARBITER_PATH, {
        "target_agent": "",
        "verdict": "none",
        "reason": "",
        "suggestion": "",
        "timestamp": datetime.now().isoformat()
    })


# ─────────────────────────────────────────────────────────────
#  ESPERAR RESPUESTA DEL AGENTE
# ─────────────────────────────────────────────────────────────
def wait_for_done(agent_name, timeout=120):
    """
    Espera la señal 'done' del agente con animación.
    Retorna (responded: bool, response_text: str)
    """
    deadline = time.time() + timeout
    dots = 0
    while time.time() < deadline:
        try:
            sig = read_json(SIGNAL_PATH)
            if sig.get("signal") == "done" and sig.get("target_agent") == agent_name:
                response = sig.get("response", "")
                return True, response
        except Exception:
            pass
        dots = (dots + 1) % 4
        label = ca(agent_name, agent_name.upper())
        print(f"  {C_GRAY}Esperando a {label}{C_GRAY}{'.' * dots}{' ' * (3-dots)}{R}",
              end="\r")
        time.sleep(0.4)

    print()
    return False, ""


# ─────────────────────────────────────────────────────────────
#  ABRIR TERMINAL POR AGENTE
# ─────────────────────────────────────────────────────────────
def open_agent_terminal(agent_name):
    """
    Abre una terminal separada por cada agente.
    Compatible con Windows, macOS y Linux.
    """
    python_exe = sys.executable
    script = AGENT_SCRIPT
    title = f"AGENTE: {agent_name.upper()}"
    system = platform.system()

    try:
        if system == "Windows":
            subprocess.Popen(
                ["start", title, "cmd", "/k",
                 python_exe, script, agent_name],
                shell=True, cwd=BASE_DIR
            )

        elif system == "Darwin":
            apple_script = (
                f'tell application "Terminal"\n'
                f'  do script "cd \\"{BASE_DIR}\\" && '
                f'\\"{python_exe}\\" \\"{script}\\" {agent_name}"\n'
                f'  activate\nend tell'
            )
            subprocess.Popen(["osascript", "-e", apple_script])

        else:  # Linux
            emulators = [
                ["gnome-terminal", "--title", title, "--",
                 python_exe, script, agent_name],
                ["xterm", "-title", title, "-e",
                 python_exe, script, agent_name],
                ["konsole", "--title", title, "-e",
                 python_exe, script, agent_name],
                ["xfce4-terminal", "--title", title, "-e",
                 f"{python_exe} {script} {agent_name}"],
                ["lxterminal", "--title", title, "-e",
                 f"{python_exe} {script} {agent_name}"],
                ["mate-terminal", "--title", title, "-e",
                 f"{python_exe} {script} {agent_name}"],
                ["tilix", "--title", title, "-e",
                 f"{python_exe} {script} {agent_name}"],
            ]
            launched = False
            for em in emulators:
                try:
                    subprocess.Popen(em, cwd=BASE_DIR,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    print(f"{C_GRAY}  └─ Terminal: {em[0]}{R}")
                    launched = True
                    break
                except FileNotFoundError:
                    continue

            if not launched:
                print(f"{C_RED}  ⚠ Sin emulador de terminal. "
                      f"Corriendo {agent_name} en background.{R}")
                subprocess.Popen(
                    [python_exe, script, agent_name],
                    cwd=BASE_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        return True

    except Exception as e:
        print(f"{C_RED}  Error abriendo terminal para {agent_name}: {e}{R}")
        log_orc(f"ERROR terminal {agent_name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────
#  RESETEAR SESIÓN
# ─────────────────────────────────────────────────────────────
def reset_session(max_iterations=20):
    """Reinicia todos los archivos de estado para una nueva sesión."""
    # State
    write_json(STATE_PATH, {
        "current_turn": "alex",
        "iteration": 0,
        "max_iterations": max_iterations,
        "conversation_active": True,
        "last_response": "",
        "start_time": datetime.now().isoformat()
    })
    # Signal
    write_json(SIGNAL_PATH, {
        "signal": "idle",
        "target_agent": "",
        "timestamp": datetime.now().isoformat()
    })
    # Arbiter
    clear_arbiter_state()
    # Conversación
    with open(CONV_PATH, "w", encoding="utf-8") as f:
        f.write(f"# Conversación Multi-Agente: Alex & Sofia\n")
        f.write(f"## Sesión: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("=== INICIO ===\n")
    # Memorias de agentes
    for agent in ["alex", "sofia"]:
        mem_path = os.path.join(BASE_DIR, "agents", agent, "memory.md")
        with open(mem_path, "w", encoding="utf-8") as f:
            f.write(f"# Memoria de {agent.capitalize()}\n")
            f.write("_Historial de mis propias respuestas. No repetir estas ideas._\n\n")
    # Logs
    for logfile in ["orchestrator.log", "alex.log", "sofia.log", "arbiter.log"]:
        log_path = os.path.join(BASE_DIR, "logs", logfile)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        open(log_path, "w").close()  # Vaciar


# ─────────────────────────────────────────────────────────────
#  MOSTRAR ENCABEZADO
# ─────────────────────────────────────────────────────────────
def print_header():
    clear()
    width = 62
    print(C_GOLD + "═" * width + R)
    print(C_GOLD + BOLD + "  ★  ORQUESTADOR CENTRAL  ★  MULTI-AGENT v2" + R)
    print(C_GOLD + "═" * width + R)
    print(f"{C_GRAY}  {ca('alex', 'Alex')} {C_GRAY}←→{R} {ca('sofia', 'Sofia')}"
          f"  ·  Árbitro: {ca('arbiter', 'Puerto 11434')}"
          f"  ·  {datetime.now().strftime('%Y-%m-%d')}{R}")
    print()

def print_architecture():
    """Muestra la arquitectura de 3 Ollamas al inicio."""
    print(f"{C_ARB}  Arquitectura de instancias Ollama:{R}")
    print(f"{C_GRAY}  ┌─────────────────────────────────────────┐{R}")
    print(f"{C_GRAY}  │  {ca('arbiter', 'Árbitro')}  → localhost:{C_ARB}11434{R}{C_GRAY}  (temp=0.3){C_GRAY}  │{R}")
    print(f"{C_GRAY}  │  {ca('alex', 'Alex   ')}  → localhost:{C_ALEX}11435{R}{C_GRAY}  (temp=0.85){C_GRAY} │{R}")
    print(f"{C_GRAY}  │  {ca('sofia', 'Sofia  ')}  → localhost:{C_SOFIA}11436{R}{C_GRAY}  (temp=0.90){C_GRAY} │{R}")
    print(f"{C_GRAY}  └─────────────────────────────────────────┘{R}")
    print()
    print(f"{C_WHITE}  Para levantar 3 instancias separadas:{R}")
    print(f"{C_GRAY}  Terminal 1: OLLAMA_HOST=0.0.0.0:11434 ollama serve{R}")
    print(f"{C_GRAY}  Terminal 2: OLLAMA_HOST=0.0.0.0:11435 ollama serve{R}")
    print(f"{C_GRAY}  Terminal 3: OLLAMA_HOST=0.0.0.0:11436 ollama serve{R}")
    print()
    print(f"{C_WHITE}  Si solo tienes 1 Ollama en 11434, los agentes lo compartirán{R}")
    print(f"{C_GRAY}  (funcional pero no completamente independiente){R}")
    print()


def print_turn_header(iteration, current_agent, max_iter):
    print(f"\n{C_ORG}{'─' * 62}{R}")
    print(f"{C_ORG}  TURNO {iteration}/{max_iter}  →  "
          f"{ca(current_agent, current_agent.upper())}{C_ORG}  ·  {ts()}{R}")
    print(f"{C_ORG}{'─' * 62}{R}")


# ─────────────────────────────────────────────────────────────
#  LOOP PRINCIPAL
# ─────────────────────────────────────────────────────────────
def orchestrate():
    print_header()
    print_architecture()

    # ── Configuración de sesión ──
    print(f"{C_WHITE}  Configuración de sesión:{R}")
    try:
        mi = input(f"{C_GRAY}  Iteraciones máximas [20]: {R}").strip()
        max_iter = int(mi) if mi else 20

        delay_in = input(f"{C_GRAY}  Pausa entre turnos en segundos [4]: {R}").strip()
        delay = float(delay_in) if delay_in else 4.0

        max_arb_rejections = 2  # Máximo rechazos del árbitro por turno antes de usar fallback

    except (ValueError, KeyboardInterrupt):
        max_iter, delay = 20, 4.0
        max_arb_rejections = 2

    print()
    log_orc(f"Sesión iniciada: max_iter={max_iter}, delay={delay}")

    # ── Reset ──
    reset_session(max_iterations=max_iter)
    time.sleep(0.3)

    # ── Abrir terminales ──
    print(f"\n{C_WHITE}  Abriendo terminales de agentes...{R}")
    for agent in ["alex", "sofia"]:
        print(f"  → {ca(agent, agent.upper())}...", end=" ", flush=True)
        ok = open_agent_terminal(agent)
        print(f"{C_GREEN}✓{R}" if ok else f"{C_RED}✗{R}")
        time.sleep(1.5)

    print(f"\n{C_GRAY}  Esperando que las terminales inicien (4s)...{R}")
    time.sleep(4)

    # ── Loop de orquestación ──
    agents = ["alex", "sofia"]
    agent_idx = 0
    total_arbiter_rejects = 0

    for iteration in range(1, max_iter + 1):
        current_agent = agents[agent_idx % 2]
        print_turn_header(iteration, current_agent, max_iter)

        arbiter_rejects_this_turn = 0
        accepted = False
        final_response = ""

        while arbiter_rejects_this_turn <= max_arb_rejections:

            is_retry = arbiter_rejects_this_turn > 0

            # ── Paso 1: Señalizar al agente ──
            if is_retry:
                print(f"{C_ORG}  [Reintento #{arbiter_rejects_this_turn}] "
                      f"Señalizando a {ca(current_agent, current_agent.upper())}...{R}")
                signal_retry(current_agent)
            else:
                print(f"{C_WHITE}  [1/3] Señalizando a "
                      f"{ca(current_agent, current_agent.upper())}...{R}")
                clear_arbiter_state()
                signal_go(current_agent)

            log_orc(f"Turno {iteration}: señal go → {current_agent}"
                    f"{' (retry)' if is_retry else ''}")

            # ── Paso 2: Esperar respuesta ──
            print(f"{C_WHITE}  [2/3] Esperando respuesta...{R}")
            responded, response_text = wait_for_done(current_agent, timeout=120)

            if not responded:
                print(f"{C_RED}  ✗ Timeout ({current_agent}). Saltando turno.{R}")
                log_orc(f"TIMEOUT turno {iteration} para {current_agent}")
                break

            if not response_text:
                print(f"{C_RED}  ✗ Respuesta vacía recibida.{R}")
                arbiter_rejects_this_turn += 1
                continue

            # ── Paso 3: Árbitro evalúa ──
            print(f"{C_WHITE}  [3/3] {ca('arbiter', 'Árbitro')} evaluando...{R}")
            accepted_by_arbiter = run_arbiter(current_agent, response_text)

            if accepted_by_arbiter:
                accepted = True
                final_response = response_text
                print(f"\n{C_GREEN}  ✓ {ca(current_agent, current_agent.upper())}: "
                      f"\"{final_response[:100]}\"{R}")
                log_orc(f"Turno {iteration} ACEPTADO. {current_agent}: '{final_response[:80]}'")
                break
            else:
                arbiter_rejects_this_turn += 1
                total_arbiter_rejects += 1
                print(f"{C_RED}  ✗ Árbitro rechazó. "
                      f"({arbiter_rejects_this_turn}/{max_arb_rejections} reintentos){R}")
                log_orc(f"Árbitro rechazó turno {iteration} para {current_agent} "
                        f"(intento {arbiter_rejects_this_turn})")

                if arbiter_rejects_this_turn > max_arb_rejections:
                    print(f"{C_ORG}  ⚠ Máximo reintentos alcanzado. "
                          f"Usando última respuesta.{R}")
                    accepted = True
                    final_response = response_text
                    log_orc(f"Forzando respuesta tras {arbiter_rejects_this_turn} rechazos")
                    break

                time.sleep(1.0)  # Pequeña pausa antes de reintento

        if not accepted or not final_response:
            print(f"{C_RED}  ✗ Turno {iteration} sin respuesta válida. Continuando.{R}")
            agent_idx += 1
            continue

        # ── Actualizar estado ──
        try:
            state = read_json(STATE_PATH)
            state["iteration"] = iteration
            state["current_turn"] = "sofia" if current_agent == "alex" else "alex"
            state["last_response"] = final_response[:100]
            write_json(STATE_PATH, state)
        except Exception as e:
            log_orc(f"Error state.json: {e}")

        # ── Verificar fin ──
        if iteration >= max_iter:
            print(f"\n{C_GREEN}  ✓ Conversación completada ({max_iter} turnos).{R}")
            break

        # ── Pausa y siguiente ──
        print(f"{C_GRAY}  Pausa de {delay}s...{R}")
        time.sleep(delay)
        agent_idx += 1

    # ── Cierre ──
    print(f"\n{C_WHITE}  Enviando señal de cierre...{R}")
    signal_stop()
    log_orc(f"Sesión finalizada. Rechazos árbitro total: {total_arbiter_rejects}")

    print(f"\n{C_GOLD}{'═' * 62}{R}")
    print(f"{C_GOLD}  SESIÓN FINALIZADA  ·  {ts()}{R}")
    print(f"{C_GOLD}  Rechazos árbitro: {total_arbiter_rejects}{R}")
    print(f"{C_GOLD}{'═' * 62}{R}")
    print(f"\n{C_GRAY}  Conversación: shared/conversation.txt{R}")
    print(f"{C_GRAY}  Logs: logs/{R}\n")


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        orchestrate()
    except KeyboardInterrupt:
        print(f"\n\n{C_RED}  Orquestador detenido manualmente.{R}")
        signal_stop()
        log_orc("Orquestador detenido manualmente.")
        sys.exit(0)
