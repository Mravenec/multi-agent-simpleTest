#!/usr/bin/env python3
"""
ORCHESTRATOR - Multi-Agent Flirt System
Central coordinator using signal-based communication
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any

class SignalBasedOrchestrator:
    def __init__(self, base_path: str):
        self.base_path = base_path
        self.shared_path = os.path.join(base_path, "shared")
        self.logs_path = os.path.join(base_path, "logs")
        self.signal_file = os.path.join(self.shared_path, "signal.json")

        # Configuration
        self.max_iterations = 20
        self.turn_pause_seconds = 3.0

        # Process tracking
        self.runners: Dict[str, subprocess.Popen] = {}
        self.running = False

        # Ensure directories exist
        os.makedirs(self.shared_path, exist_ok=True)
        os.makedirs(self.logs_path, exist_ok=True)

    def initialize_signal_system(self) -> None:
        """Initialize the signal coordination system"""
        signal_data = {
            "signal": "idle",
            "target": "",
            "timestamp": datetime.now().isoformat(),
            "iteration": 0
        }
        self._write_signal(signal_data)

    def _read_signal(self) -> dict:
        """Read signal file safely"""
        try:
            with open(self.signal_file, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error reading signal: {e}")
            return {"signal": "idle", "target": "", "timestamp": "", "iteration": 0}

    def _write_signal(self, signal_data: dict) -> None:
        """Write signal file safely"""
        try:
            with open(self.signal_file, "w", encoding='utf-8') as f:
                json.dump(signal_data, f, indent=2)
        except Exception as e:
            print(f"❌ Error writing signal: {e}")

    def log_action(self, action: str, details: str = "") -> None:
        """Log orchestrator actions"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {action}"
        if details:
            log_entry += f" - {details}"

        log_file = os.path.join(self.logs_path, "orchestrator.log")
        try:
            with open(log_file, "a", encoding='utf-8') as f:
                f.write(log_entry + "\n")
        except Exception as e:
            print(f"❌ Error logging: {e}")

    def start_agent_runners(self) -> bool:
        """Start agent runners in separate terminals"""
        print("  Abriendo terminales de agentes...")
        agents = ["alex", "sofia"]
        success = True

        for agent in agents:
            try:
                print(f"  → {agent.upper()}...", end=" ")
                runner_process = self.launch_runner(agent)
                if runner_process:
                    self.runners[agent] = runner_process
                    print("✓")
                    self.log_action(f"RUNNER_STARTED", f"{agent} (PID: {runner_process.pid})")
                else:
                    print("✗")
                    success = False
            except Exception as e:
                print(f"✗ Error: {e}")
                success = False

        return success

    def launch_runner(self, agent_name: str) -> Optional[subprocess.Popen]:
        """Launch agent runner in new terminal"""
        runner_script = os.path.join(self.base_path, "agent_runner.py")

        if not os.path.exists(runner_script):
            print(f"❌ Runner script not found: {runner_script}")
            return None

        try:
            # Launch in new terminal window based on OS
            if sys.platform == "win32":
                # Windows CMD
                cmd = f'start cmd /k "cd /d {self.base_path} && python {runner_script} {agent_name}"'
                return subprocess.Popen(cmd, shell=True)
            elif sys.platform == "darwin":
                # macOS Terminal.app
                cmd = f'osascript -e \'tell app "Terminal" to do script "cd {self.base_path} && python3 {runner_script} {agent_name}"\''
                return subprocess.Popen(cmd, shell=True)
            else:
                # Linux - try gnome-terminal, xterm, konsole
                terminals = ["gnome-terminal", "xterm", "konsole", "terminator"]
                for terminal in terminals:
                    try:
                        cmd = f'{terminal} -- bash -c "cd {self.base_path} && python3 {runner_script} {agent_name}; exec bash"'
                        return subprocess.Popen(cmd, shell=True)
                    except FileNotFoundError:
                        continue

                # Fallback to background process
                print("⚠️ No GUI terminal found, running in background")
                return subprocess.Popen(
                    [sys.executable, runner_script, agent_name],
                    cwd=self.base_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

        except Exception as e:
            print(f"❌ Error launching runner: {e}")
            return None

    def signal_agent_turn(self, agent_name: str, iteration: int) -> None:
        """Signal agent to take their turn"""
        signal_data = {
            "signal": "go",
            "target": agent_name,
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration
        }
        self._write_signal(signal_data)
        print(f"  [1/3] Señalizando a {agent_name.upper()}...")

    def wait_for_agent_response(self, agent_name: str, timeout: int = 30) -> bool:
        """Wait for agent to complete their turn"""
        print(f"  [2/3] Esperando respuesta...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            signal_data = self._read_signal()

            if signal_data.get("signal") == "done" and signal_data.get("target") == agent_name:
                print(f"  [3/3] ✅ {agent_name.upper()} completó su turno")
                return True

            time.sleep(0.5)

        print(f"  ✗ Timeout esperando a {agent_name.upper()}. Reintentando señal...")
        return False

    def load_state(self) -> Dict[str, Any]:
        """Load system state"""
        state_file = os.path.join(self.shared_path, "state.json")
        try:
            with open(state_file, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return self._get_default_state()

    def save_state(self, state: Dict[str, Any]) -> None:
        """Save system state"""
        state_file = os.path.join(self.shared_path, "state.json")
        try:
            with open(state_file, "w", encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving state: {e}")

    def _get_default_state(self) -> Dict[str, Any]:
        """Get default system state"""
        return {
            "current_turn": "alex",
            "iteration": 0,
            "max_iterations": self.max_iterations,
            "conversation_active": True,
            "last_response": "",
            "start_time": ""
        }

    def handle_first_turn(self, state: Dict[str, Any]) -> None:
        """Handle the first turn (Alex starts conversation)"""
        initial_message = "Hola Sofia, vi tu perfil de diseñadora. ¿Qué tipo de proyectos te apasionan más?"
        self.update_conversation("alex", initial_message)
        self.update_memory("alex", initial_message)

        state["iteration"] += 1
        state["current_turn"] = "sofia"
        state["start_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.save_state(state)

    def update_conversation(self, agent_name: str, response: str) -> None:
        """Update conversation log"""
        conv_path = os.path.join(self.shared_path, "conversation.txt")
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            with open(conv_path, "a", encoding='utf-8') as f:
                f.write(f"\n\n[{timestamp}] {agent_name.upper()}:\n{response}\n")
        except Exception as e:
            print(f"❌ Error updating conversation: {e}")

    def update_memory(self, agent_name: str, response: str) -> None:
        """Update agent memory"""
        memory_path = os.path.join(self.base_path, "agents", agent_name, "memory.md")
        try:
            with open(memory_path, "r", encoding='utf-8') as f:
                current_memory = f.read()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_memory = f"{current_memory}\n\n[{timestamp}] {response}"
            with open(memory_path, "w", encoding='utf-8') as f:
                f.write(new_memory)
        except Exception as e:
            print(f"❌ Error updating {agent_name} memory: {e}")

    def run_conversation_loop(self) -> None:
        """Main conversation orchestration loop"""
        state = self.load_state()

        if not state["conversation_active"] or state["iteration"] >= state["max_iterations"]:
            return

        iteration = state["iteration"] + 1
        current_agent = state["current_turn"]

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n────────────────────────────────────────────────────────────")
        print(f"  TURNO {iteration}/{self.max_iterations}  →  {current_agent.upper()}  ·  {timestamp}")
        print(f"────────────────────────────────────────────────────────────")

        # Handle first turn
        if state["iteration"] == 0 and current_agent == "alex":
            self.handle_first_turn(state)
            print(f"  📝 Alex inició conversación")
            return

        # Signal agent to take turn
        self.signal_agent_turn(current_agent, iteration)

        # Wait for response
        if self.wait_for_agent_response(current_agent):
            # Update state for next turn
            state["iteration"] += 1
            state["current_turn"] = "sofia" if current_agent == "alex" else "alex"
            self.save_state(state)
            self.log_action("TURN_COMPLETED", f"{current_agent} -> {state['current_turn']}")

            # Pause between turns
            if state["iteration"] < state["max_iterations"]:
                print(f"  ⏳ Pausa de {self.turn_pause_seconds}s...")
                time.sleep(self.turn_pause_seconds)
        else:
            self.log_action("TURN_TIMEOUT", current_agent)

    def run_orchestrator(self) -> None:
        """Main orchestrator execution"""
        print("════════════════════════════════════════════════════════════")
        print("  ★  ORQUESTADOR CENTRAL  ★  MULTI-AGENT FLIRT SYSTEM")
        print("════════════════════════════════════════════════════════════")
        print(f"  Alex  ←→  Sofia  ·  {datetime.now().strftime('%Y-%m-%d')}")
        print()
        print("  Configuración de sesión:")
        print(f"  Iteraciones máximas [20]: {self.max_iterations}")
        print(f"  Pausa entre turnos en segundos [3]: {self.turn_pause_seconds}")
        print()
        print(f"  Iniciando sesión con {self.max_iterations} turnos y {self.turn_pause_seconds}s de pausa...")
        print()

        self.log_action("ORCHESTRATOR_STARTED", f"max_iter={self.max_iterations}, pause={self.turn_pause_seconds}")

        try:
            # Initialize signal system
            self.initialize_signal_system()

            # Start agent runners
            if not self.start_agent_runners():
                print("❌ Failed to start agent runners")
                return

            print("  Esperando que las terminales estén listas (3s)...")
            time.sleep(3)

            # Main conversation loop
            while self.running:
                self.run_conversation_loop()

                # Check if conversation is complete
                state = self.load_state()
                if not state["conversation_active"] or state["iteration"] >= state["max_iterations"]:
                    print("\n🏁 Conversación completada")
                    break

                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n  Orquestador detenido manualmente.")
            self.log_action("ORCHESTRATOR_STOPPED", "KeyboardInterrupt")
        except Exception as e:
            print(f"❌ Error en orquestador: {e}")
            self.log_action("ORCHESTRATOR_ERROR", str(e))
        finally:
            self.stop_runners()
            print("\n🏁 Orquestador finalizado")

    def stop_runners(self) -> None:
        """Stop all agent runners"""
        print("🛑 Deteniendo runners de agentes...")
        for agent, process in self.runners.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"✅ {agent.capitalize()} runner detenido")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"🔨 Force killed {agent} runner")
            except Exception as e:
                print(f"❌ Error stopping {agent}: {e}")

if __name__ == "__main__":
    base_path = os.path.dirname(os.path.abspath(__file__))
    orchestrator = SignalBasedOrchestrator(base_path)
    orchestrator.running = True
    orchestrator.run_orchestrator()
