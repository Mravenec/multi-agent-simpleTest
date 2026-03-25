#!/usr/bin/env python3
import json
import os
import subprocess
import time
from datetime import datetime

class MultiAgentOrchestrator:
    def __init__(self, base_path):
        self.base_path = base_path
        self.shared_path = os.path.join(base_path, "shared")
        self.agents_path = os.path.join(base_path, "agents")
        self.prompts_path = os.path.join(base_path, "prompts")
        self.logs_path = os.path.join(base_path, "logs")
        
    def load_state(self):
        with open(os.path.join(self.shared_path, "state.json"), "r") as f:
            return json.load(f)
    
    def save_state(self, state):
        with open(os.path.join(self.shared_path, "state.json"), "w") as f:
            json.dump(state, f, indent=2)
    
    def load_agent_config(self, agent_name):
        config_path = os.path.join(self.agents_path, agent_name, "config.json")
        with open(config_path, "r") as f:
            return json.load(f)
    
    def load_agent_personality(self, agent_name):
        personality_path = os.path.join(self.agents_path, agent_name, "personality.md")
        with open(personality_path, "r") as f:
            return f.read()
    
    def load_agent_memory(self, agent_name):
        memory_path = os.path.join(self.agents_path, agent_name, "memory.md")
        with open(memory_path, "r") as f:
            return f.read()
    
    def load_conversation(self):
        conv_path = os.path.join(self.shared_path, "conversation.txt")
        with open(conv_path, "r") as f:
            return f.read()
    
    def load_system_base(self):
        system_path = os.path.join(self.prompts_path, "system_base.md")
        with open(system_path, "r") as f:
            return f.read()
    
    def build_prompt(self, agent_name):
        system_base = self.load_system_base()
        personality = self.load_agent_personality(agent_name)
        memory = self.load_agent_memory(agent_name)
        conversation = self.load_conversation()
        
        prompt = f"""{system_base}

{personality}

{memory}

Conversación anterior:
{conversation}

RESPONDE MÁXIMO 2 LÍNEAS. Sé directo y conciso."""
        
        return prompt
    
    def call_ollama(self, prompt, model, temperature=0.7):
        try:
            cmd = ["ollama", "run", model, prompt]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"Error: {result.stderr}"
        except subprocess.TimeoutExpired:
            return "Error: Timeout al llamar al modelo"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def update_conversation(self, agent_name, response):
        conv_path = os.path.join(self.shared_path, "conversation.txt")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        with open(conv_path, "a") as f:
            f.write(f"\n\n[{timestamp}] {agent_name.upper()}:\n{response}\n")
    
    def update_memory(self, agent_name, new_response):
        memory_path = os.path.join(self.agents_path, agent_name, "memory.md")
        with open(memory_path, "r") as f:
            current_memory = f.read()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_memory = f"{current_memory}\n\n[{timestamp}] {new_response}"
        
        with open(memory_path, "w") as f:
            f.write(new_memory)
    
    def switch_turn(self, current_agent):
        return "sofia" if current_agent == "alex" else "alex"
    
    def run_turn(self):
        state = self.load_state()
        
        if not state["conversation_active"] or state["iteration"] >= state["max_iterations"]:
            print("Conversación terminada")
            return False
        
        current_agent = state["current_turn"]
        print(f"Turno de: {current_agent}")
        
        # Load agent config
        config = self.load_agent_config(current_agent)
        
        # Build prompt
        prompt = self.build_prompt(current_agent)
        
        # Call model
        response = self.call_ollama(prompt, config["model"], config["temperature"])
        
        if response and not response.startswith("Error:"):
            # Check for completion keywords
            completion_keywords = ["sí", "quiero", "vamos", "claro", "ahora", "juntos"]
            response_lower = response.lower()
            
            if any(keyword in response_lower for keyword in completion_keywords):
                print(f"¡Objetivo alcanzado! {current_agent}: {response}")
                state["conversation_active"] = False
                state["completed"] = True
                state["completion_response"] = response
                self.save_state(state)
                return False
            
            # Update conversation
            self.update_conversation(current_agent, response)
            
            # Update memory
            self.update_memory(current_agent, response)
            
            # Update state
            state["iteration"] += 1
            state["current_turn"] = self.switch_turn(current_agent)
            state["last_response"] = response
            
            self.save_state(state)
            
            print(f"{current_agent}: {response}")
            return True
        else:
            print(f"Error en respuesta de {current_agent}: {response}")
            return False
    
    def log_interaction(self, message):
        log_path = os.path.join(self.logs_path, "run.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

if __name__ == "__main__":
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    orchestrator = MultiAgentOrchestrator(base_path)
    
    print("Iniciando conversación multi-agente...")
    
    try:
        while orchestrator.run_turn():
            time.sleep(2)  # Pausa reducida para conversación más ágil
    except KeyboardInterrupt:
        print("\nConversación interrumpida por usuario")
    except Exception as e:
        print(f"Error: {e}")
