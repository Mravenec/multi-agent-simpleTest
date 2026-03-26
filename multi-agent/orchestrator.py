"""
orchestrator.py — Terminal Central de Orquestación
Abre las terminales de cada agente y coordina los turnos en orden lógico.

Uso: python orchestrator.py
"""

import os
import sys
import json
import time
import subprocess
import platform
from datetime import datetime

# ─────────────────────────────────────────────
#  COLORES ANSI (cross-platform)
# ─────────────────────────────────────────────
def enable_ansi_windows():
    """Habilita ANSI en Windows 10+."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass

enable_ansi_windows()

R  = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"

# Paleta orquestador
ORC_HDR  = "\033[38;5;220m"   # Dorado
ORC_INFO = "\033[38;5;250m"   # Blanco suave
ORC_TURN = "\033[38;5;214m"   # Naranja
ORC_OK   = "\033[38;5;82m"    # Verde brillante
ORC_ERR  = "\033[38;5;196m"   # Rojo
ORC_DIM  = "\033[38;5;240m"   # Gris oscuro
ORC_ALEX = "\033[38;5;75m"    # Azul claro
ORC_SOFIA= "\033[38;5;213m"   # Rosa/Magenta

def color_agent(name, text):
    return (ORC_ALEX if name == "alex" else ORC_SOFIA) + text + R

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SIGNAL_PATH = os.path.join(BASE_DIR, "shared", "signal.json")
STATE_PATH  = os.path.join(BASE_DIR, "shared", "state.json")
CONV_PATH   = os.path.join(BASE_DIR, "shared", "conversation.txt")
LOG_PATH    = os.path.join(BASE_DIR, "logs", "orchestrator.log")
AGENT_SCRIPT= os.path.join(BASE_DIR, "agents", "{agent_name}", "agent_terminal.py")

# ─────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
#  ABRIR TERMINAL POR AGENTE (cross-platform)
# ─────────────────────────────────────────────
def open_agent_terminal(agent_name):
    """
    Abre una nueva ventana de terminal según el OS y lanza agent_runner.py.
    Compatible: Windows (CMD), macOS (Terminal.app), Linux (gnome-terminal/xterm/konsole/etc.)
    """
    python_exe = sys.executable
    script = AGENT_SCRIPT.format(agent_name=agent_name)
    title = f"AGENTE: {agent_name.upper()}"
    system = platform.system()

    try:
        if system == "Windows":
            # Windows: usar subprocess con argumentos separados para evitar problemas de quoting
            subprocess.Popen(
                ["start", title, "cmd", "/k", python_exe, script, agent_name],
                shell=True,
                cwd=BASE_DIR
            )

        elif system == "Darwin":
            # macOS: AppleScript abre nueva ventana de Terminal
            apple_script = (
                f'tell application "Terminal"\n'
                f'  do script "cd \\"{BASE_DIR}\\" && \\"{python_exe}\\" \\"{script}\\" {agent_name}"\n'
                f'  activate\n'
                f'end tell'
            )
            subprocess.Popen(["osascript", "-e", apple_script])

        else:
            # Linux: intentar múltiples emuladores en orden de preferencia
            emulators = [
                ["gnome-terminal", "--title", title, "--", python_exe, script, agent_name],
                ["xterm",          "-title",  title, "-e", python_exe, script, agent_name],
                ["konsole",        "--title", title, "-e", python_exe, script, agent_name],
                ["xfce4-terminal", "--title", title, "-e", f"{python_exe} {script} {agent_name}"],
                ["lxterminal",     "--title", title, "-e", f"{python_exe} {script} {agent_name}"],
                ["mate-terminal",  "--title", title, "-e", f"{python_exe} {script} {agent_name}"],
            ]
            launched = False
            for em in emulators:
                try:
                    subprocess.Popen(em, cwd=BASE_DIR,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    launched = True
                    print(f"{ORC_DIM}  └─ Terminal: {em[0]}{R}")
                    break
                except FileNotFoundError:
                    continue
            if not launched:
                # Último recurso: abrir en background sin ventana
                print(f"{ORC_ERR}  ⚠ No se encontró emulador de terminal. "
                      f"Corriendo {agent_name} en background.{R}")
                subprocess.Popen(
                    [python_exe, script, agent_name],
                    cwd=BASE_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        return True
    except Exception as e:
        print(f"{ORC_ERR}  Error abriendo terminal para {agent_name}: {e}{R}")
        log_orc(f"ERROR abriendo terminal {agent_name}: {e}")
        return False


# ─────────────────────────────────────────────
#  SEÑALIZAR AGENTE
# ─────────────────────────────────────────────
def signal_agent(agent_name):
    """Envía señal 'go' al agente indicado."""
    write_json(SIGNAL_PATH, {
        "signal": "go",
        "target_agent": agent_name,
        "timestamp": datetime.now().isoformat()
    })

def signal_stop():
    """Envía señal de parada a todos los agentes."""
    write_json(SIGNAL_PATH, {
        "signal": "stop",
        "target_agent": "",
        "timestamp": datetime.now().isoformat()
    })


# ─────────────────────────────────────────────
#  ESPERAR RESPUESTA DEL AGENTE
# ─────────────────────────────────────────────
def wait_for_done(agent_name, timeout=60):
    """
    Espera a que el agente señale 'done'.
    Retorna True si respondió, False si timeout.
    """
    deadline = time.time() + timeout
    dots = 0
    while time.time() < deadline:
        try:
            sig = read_json(SIGNAL_PATH)
            if sig.get("signal") == "done" and sig.get("target_agent") == agent_name:
                return True
        except Exception:
            pass
        # Animación de espera
        dots = (dots + 1) % 4
        waiting_str = f"  Esperando a {color_agent(agent_name, agent_name.upper())}{'.' * dots}{' ' * (3 - dots)}"
        print(waiting_str, end="\r")
        time.sleep(0.5)

    print()  # Nueva línea tras animación
    return False


# ─────────────────────────────────────────────
#  LEER ÚLTIMA RESPUESTA DE LA CONVERSACIÓN
# ─────────────────────────────────────────────
def get_last_line_from_conv():
    """Lee la última línea significativa del archivo de conversación."""
    try:
        with open(CONV_PATH, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        # Buscar últimas líneas con mensajes reales
        for line in reversed(lines):
            if not line.startswith("#") and not line.startswith("=") and len(line) > 5:
                return line
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────
#  MOSTRAR ENCABEZADO DEL ORQUESTADOR
# ─────────────────────────────────────────────
def print_header():
    clear()
    width = 60
    print(ORC_HDR + "═" * width + R)
    print(ORC_HDR + BOLD + "  ★  ORQUESTADOR CENTRAL  ★  MULTI-AGENT FLIRT SYSTEM" + R)
    print(ORC_HDR + "═" * width + R)
    print(f"{ORC_DIM}  Alex  ←→  Sofia  ·  {datetime.now().strftime('%Y-%m-%d')}{R}")
    print()


def print_turn_header(iteration, current_agent, max_iter):
    print(f"\n{ORC_TURN}{'─' * 60}{R}")
    print(f"{ORC_TURN}  TURNO {iteration}/{max_iter}  →  "
          f"{color_agent(current_agent, current_agent.upper())}{ORC_TURN}  ·  {ts()}{R}")
    print(f"{ORC_TURN}{'─' * 60}{R}")


# ─────────────────────────────────────────────
#  RESETEAR ESTADO
# ─────────────────────────────────────────────
def reset_state(max_iterations=20):
    """Reinicia el estado y la conversación para una nueva sesión."""
    write_json(STATE_PATH, {
        "current_turn": "alex",
        "iteration": 0,
        "max_iterations": max_iterations,
        "conversation_active": True,
        "last_response": "",
        "start_time": datetime.now().isoformat()
    })
    write_json(SIGNAL_PATH, {
        "signal": "idle",
        "target_agent": "",
        "timestamp": datetime.now().isoformat()
    })
    # Resetear conversación
    with open(CONV_PATH, "w", encoding="utf-8") as f:
        f.write(f"# Conversación Multi-Agente entre Alex y Sofia\n")
        f.write(f"## Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("=== INICIO DE CONVERSACIÓN ===\n")
    # Resetear memorias
    for agent in ["alex", "sofia"]:
        mem_path = os.path.join(BASE_DIR, "agents", agent, "memory.md")
        with open(mem_path, "w", encoding="utf-8") as f:
            f.write(f"# Memoria de {agent.capitalize()}\nInicio de la cita.\n")


# ─────────────────────────────────────────────
#  LOOP PRINCIPAL DE ORQUESTACIÓN
# ─────────────────────────────────────────────
def orchestrate():
    print_header()

    # ── Preguntar parámetros ──
    print(f"{ORC_INFO}  Configuración de sesión:{R}")
    try:
        max_iter_input = input(f"{ORC_DIM}  Iteraciones máximas [20]: {R}").strip()
        max_iter = int(max_iter_input) if max_iter_input else 20
        delay_input = input(f"{ORC_DIM}  Pausa entre turnos en segundos [3]: {R}").strip()
        delay = float(delay_input) if delay_input else 3.0
    except (ValueError, KeyboardInterrupt):
        max_iter = 20
        delay = 3.0

    print()
    print(f"{ORC_INFO}  Iniciando sesión con {max_iter} turnos y {delay}s de pausa...{R}")
    log_orc(f"Sesión iniciada. max_iter={max_iter}, delay={delay}")

    # ── Resetear estado ──
    reset_state(max_iterations=max_iter)
    time.sleep(0.5)

    # ── Abrir terminales de agentes ──
    print(f"\n{ORC_INFO}  Abriendo terminales de agentes...{R}")
    for agent in ["alex", "sofia"]:
        print(f"  → {color_agent(agent, agent.upper())}...", end=" ")
        ok = open_agent_terminal(agent)
        print(f"{ORC_OK}✓{R}" if ok else f"{ORC_ERR}✗{R}")
        time.sleep(1.2)  # Dar tiempo para que cada terminal abra

    print(f"\n{ORC_DIM}  Esperando que las terminales estén listas (3s)...{R}")
    time.sleep(3)

    # ── Loop de orquestación ──
    agents = ["alex", "sofia"]
    agent_index = 0  # Empieza Alex

    for iteration in range(1, max_iter + 1):
        current_agent = agents[agent_index % 2]
        print_turn_header(iteration, current_agent, max_iter)

        # ── Paso 1: Señalar al agente ──
        print(f"{ORC_INFO}  [1/3] Señalizando a {color_agent(current_agent, current_agent.upper())}...{R}")
        signal_agent(current_agent)
        log_orc(f"Turno {iteration}: señal enviada a {current_agent}")

        # ── Paso 2: Esperar respuesta ──
        print(f"{ORC_INFO}  [2/3] Esperando respuesta...{R}")
        responded = wait_for_done(current_agent, timeout=90)

        if not responded:
            print(f"{ORC_ERR}  ✗ Timeout esperando a {current_agent}. Reintentando señal...{R}")
            log_orc(f"TIMEOUT en turno {iteration} para {current_agent}")
            # Reintentar una vez
            signal_agent(current_agent)
            responded = wait_for_done(current_agent, timeout=45)
            if not responded:
                print(f"{ORC_ERR}  ✗ Segundo timeout. Saltando turno.{R}")
                log_orc(f"Turno {iteration} saltado por doble timeout")
                agent_index += 1
                continue

        # ── Paso 3: Mostrar resultado y pausar ──
        last_line = get_last_line_from_conv()
        print(f"\n{ORC_INFO}  [3/3] {color_agent(current_agent, current_agent.upper())} respondió:{R}")
        if last_line:
            print(f"         {ORC_OK}\"{last_line}\"{R}")

        log_orc(f"Turno {iteration} completado. {current_agent}: '{last_line}'")

        # ── Actualizar estado ──
        try:
            state = read_json(STATE_PATH)
            state["iteration"] = iteration
            state["current_turn"] = "sofia" if current_agent == "alex" else "alex"
            state["last_response"] = last_line
            write_json(STATE_PATH, state)
        except Exception as e:
            log_orc(f"Error actualizando state.json: {e}")

        # ── Verificar fin ──
        if iteration >= max_iter:
            print(f"\n{ORC_OK}  ✓ Conversación completada ({max_iter} turnos).{R}")
            break

        # ── Pausa entre turnos ──
        print(f"{ORC_DIM}  Pausa de {delay}s antes del siguiente turno...{R}")
        time.sleep(delay)

        agent_index += 1

    # ── Señal de stop a todos los agentes ──
    print(f"\n{ORC_INFO}  Enviando señal de cierre a agentes...{R}")
    signal_stop()
    log_orc("Sesión finalizada. Señal stop enviada.")

    print(f"\n{ORC_HDR}{'═' * 60}{R}")
    print(f"{ORC_HDR}  SESIÓN FINALIZADA  ·  {ts()}{R}")
    print(f"{ORC_HDR}{'═' * 60}{R}")
    print(f"\n{ORC_DIM}  Conversación guardada en: shared/conversation.txt{R}")
    print(f"{ORC_DIM}  Logs en: logs/{R}\n")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    try:
        orchestrate()
    except KeyboardInterrupt:
        print(f"\n\n{ORC_ERR}  Orquestador detenido manualmente.{R}")
        signal_stop()
        log_orc("Orquestador detenido manualmente.")
        sys.exit(0)
