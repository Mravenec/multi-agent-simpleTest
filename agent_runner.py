#!/usr/bin/env python3
"""
AGENT RUNNER - Multi-Agent Flirt System
Generic runner for agent terminals with signal-based coordination
"""
import json
import os
import sys
import time
import subprocess
from datetime import datetime
from typing import Optional

class AgentRunner:
    def __init__(self, base_path: str, agent_name: str):
        self.base_path = base_path
        self.agent_name = agent_name
        self.shared_path = os.path.join(base_path, "shared")
        self.logs_path = os.path.join(base_path, "logs")
        self.signal_file = os.path.join(self.shared_path, "signal.json")

        # Ensure directories exist
        os.makedirs(self.logs_path, exist_ok=True)
        os.makedirs(self.shared_path, exist_ok=True)

        # Initialize signal file
        self._initialize_signal()

    def _initialize_signal(self) -> None:
        """Initialize signal file if it doesn't exist"""
        if not os.path.exists(self.signal_file):
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
        """Log action to agent-specific log file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {action}"
        if details:
            log_entry += f" - {details}"

        log_file = os.path.join(self.logs_path, f"{self.agent_name}.log")
        try:
            with open(log_file, "a", encoding='utf-8') as f:
                f.write(log_entry + "\n")
        except Exception as e:
            print(f"❌ Error logging: {e}")

    def wait_for_signal(self, target_agent: str, timeout: int = 30) -> bool:
        """Wait for signal targeting this agent"""
        start_time = time.time()
        print(f"⏳ Waiting for signal targeting {target_agent}...")

        while time.time() - start_time < timeout:
            signal_data = self._read_signal()

            if signal_data.get("signal") == "go" and signal_data.get("target") == target_agent:
                print(f"✅ Signal received for {target_agent}")
                return True

            time.sleep(0.5)

        print(f"⏰ Timeout waiting for {target_agent} signal")
        return False

    def signal_done(self, agent_name: str) -> None:
        """Signal that agent has completed its turn"""
        signal_data = {
            "signal": "done",
            "target": agent_name,
            "timestamp": datetime.now().isoformat(),
            "iteration": self._read_signal().get("iteration", 0)
        }
        self._write_signal(signal_data)
        print(f"📤 Signal sent: {agent_name} done")

    def launch_agent_terminal(self) -> Optional[subprocess.Popen]:
        """Launch agent terminal in new window"""
        agent_script = os.path.join(self.base_path, "agents", self.agent_name, "agent_terminal.py")

        if not os.path.exists(agent_script):
            print(f"❌ Agent script not found: {agent_script}")
            return None

        try:
            # Launch in new terminal window based on OS
            if sys.platform == "win32":
                # Windows CMD
                cmd = f'start cmd /k "cd /d {self.base_path} && python {agent_script}"'
                return subprocess.Popen(cmd, shell=True)
            elif sys.platform == "darwin":
                # macOS Terminal.app
                cmd = f'osascript -e \'tell app "Terminal" to do script "cd {self.base_path} && python3 {agent_script}"\''
                return subprocess.Popen(cmd, shell=True)
            else:
                # Linux - try gnome-terminal, xterm, konsole
                terminals = ["gnome-terminal", "xterm", "konsole", "terminator"]
                for terminal in terminals:
                    try:
                        cmd = f'{terminal} -- bash -c "cd {self.base_path} && python3 {agent_script}; exec bash"'
                        return subprocess.Popen(cmd, shell=True)
                    except FileNotFoundError:
                        continue

                # Fallback to background process
                print("⚠️ No GUI terminal found, running in background")
                return subprocess.Popen(
                    [sys.executable, agent_script],
                    cwd=self.base_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

        except Exception as e:
            print(f"❌ Error launching agent terminal: {e}")
            return None

    def run(self) -> None:
        """Main runner loop"""
        print(f"🚀 AGENT RUNNER for {self.agent_name.upper()} started")
        print(f"📁 Base path: {self.base_path}")
        print(f"📡 Signal file: {self.signal_file}")
        print("=" * 50)

        self.log_action("RUNNER_STARTED")

        try:
            # Launch agent terminal
            agent_process = self.launch_agent_terminal()
            if not agent_process:
                print("❌ Failed to launch agent terminal")
                return

            print(f"✅ Agent terminal launched (PID: {agent_process.pid})")

            # Main coordination loop
            while True:
                # Wait for signal targeting this agent
                if self.wait_for_signal(self.agent_name):
                    self.log_action("SIGNAL_RECEIVED")

                    # Signal completion after processing
                    time.sleep(1)  # Brief pause for processing
                    self.signal_done(self.agent_name)
                    self.log_action("SIGNAL_SENT_DONE")

                time.sleep(0.5)  # Poll interval

        except KeyboardInterrupt:
            print(f"\n🛑 Agent runner for {self.agent_name} stopped by user")
            self.log_action("RUNNER_STOPPED", "KeyboardInterrupt")
        except Exception as e:
            print(f"❌ Agent runner error: {e}")
            self.log_action("RUNNER_ERROR", str(e))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent_runner.py <agent_name>")
        sys.exit(1)

    agent_name = sys.argv[1].lower()
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    runner = AgentRunner(base_path, agent_name)
    runner.run()
