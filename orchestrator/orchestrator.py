import json
import os
import subprocess
import time
import re
from datetime import datetime

class MultiAgentOrchestrator:
    def __init__(self, base_path):
        self.base_path = base_path
        self.shared_path = os.path.join(base_path, "shared")
        self.agents_path = os.path.join(base_path, "agents")
        self.prompts_path = os.path.join(base_path, "prompts")
        self.logs_path = os.path.join(base_path, "logs")
        
    def load_state(self):
        with open(os.path.join(self.shared_path, "state.json"), "r", encoding='utf-8') as f:
            return json.load(f)
    
    def save_state(self, state):
        with open(os.path.join(self.shared_path, "state.json"), "w", encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    
    def load_agent_config(self, agent_name):
        config_path = os.path.join(self.agents_path, agent_name, "config.json")
        with open(config_path, "r", encoding='utf-8') as f:
            return json.load(f)
    
    def load_agent_personality(self, agent_name):
        personality_path = os.path.join(self.agents_path, agent_name, "personality.md")
        with open(personality_path, "r", encoding='utf-8') as f:
            return f.read()
    
    def load_agent_memory(self, agent_name):
        memory_path = os.path.join(self.agents_path, agent_name, "memory.md")
        with open(memory_path, "r", encoding='utf-8') as f:
            return f.read()
    
    def load_conversation(self):
        conv_path = os.path.join(self.shared_path, "conversation.txt")
        with open(conv_path, "r", encoding='utf-8') as f:
            return f.read()
    
    def load_system_base(self):
        system_path = os.path.join(self.prompts_path, "system_base.md")
        with open(system_path, "r", encoding='utf-8') as f:
            return f.read()
    
    def build_prompt(self, agent_name):
        # Tomamos solo la primera línea de la personalidad (resumen)
        personality = self.load_agent_personality(agent_name).split('\n')[1] # Tomar la línea del ID
        conversation = self.load_conversation()
        
        # Últimos 2 mensajes para contexto mínimo
        lines = [l.strip() for l in conversation.split('\n') if l.strip()]
        last_msgs = "\n".join(lines[-2:]) if len(lines) > 2 else "\n".join(lines)

        # Prompt ultra-ligero para 0.5B en CPU
        prompt = f"""Tinder: {personality}
Chat:
{last_msgs}
{agent_name.upper()}:"""
        
        return prompt
    
    def call_ollama(self, prompt, model, temperature=0.7):
        try:
            # Usar la API HTTP de Ollama para evitar el overhead del CLI
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 100, # Limitar longitud para velocidad
                    "stop": ["\n", "Alex:", "Sofia:", "ALEX:", "SOFIA:"]
                }
            }
            
            # Usar curl para no depender de librerías externas como 'requests'
            import json
            payload_json = json.dumps(payload).replace('"', '\\"')
            cmd = f'curl -s -X POST http://localhost:11434/api/generate -d "{payload_json}"'
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, encoding='utf-8')
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("response", "").strip()
            else:
                return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def update_conversation(self, agent_name, response):
        conv_path = os.path.join(self.shared_path, "conversation.txt")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        with open(conv_path, "a", encoding='utf-8') as f:
            f.write(f"\n\n[{timestamp}] {agent_name.upper()}:\n{response}\n")
    
    def update_memory(self, agent_name, new_response):
        memory_path = os.path.join(self.agents_path, agent_name, "memory.md")
        with open(memory_path, "r", encoding='utf-8') as f:
            current_memory = f.read()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_memory = f"{current_memory}\n\n[{timestamp}] {new_response}"
        
        with open(memory_path, "w", encoding='utf-8') as f:
            f.write(new_memory)
    
    def clean_response(self, response, agent_name):
        if not response: return ""
        
        lines = response.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Cortar si aparecen etiquetas de sistema
            meta_labels = ["CONVERSACIÓN PREVIA:", "PERSONALIDAD:", "CHAT DE TINDER:", "ESTA ES UNA FICCIÓN"]
            if any(label in line.upper() for label in meta_labels):
                break

            # Cortar si el otro agente intenta hablar
            if any(line.upper().startswith(name.upper()) for name in ["ALEX", "SOFIA"]):
                if line.upper().startswith(agent_name.upper()):
                    # Limpiamos el prefijo si es propio
                    line = re.sub(f"^{agent_name.upper()}:?", "", line, flags=re.IGNORECASE).strip()
                else:
                    break # Hallucinación de otro agente, paramos
            
            if line:
                clean_lines.append(line)
                
        # Retornamos los párrafos encontrados (máximo 2 para no ser pesados)
        return "\n".join(clean_lines[:2]).strip()

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
            # Clean response to enforce turns
            response = self.clean_response(response, current_agent)

            # Check for completion keywords
            completion_keywords = ["sexo", "hotel", "cama", "desnudo", "deseo"]
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
        with open(log_path, "a", encoding='utf-8') as f:
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
