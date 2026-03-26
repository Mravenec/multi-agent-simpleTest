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
        traits = "Directo, ingenioso" if agent_name == "alex" else "Aventurera, juguetona"
        conversation = self.load_conversation()
        
        # Historial muy corto para evitar que el tono "asistente" se contagie
        lines = [l.strip() for l in conversation.split('\n') if l.strip()]
        chat_lines = [l for l in lines if ":" in l and any(n in l.upper() for n in ["ALEX", "SOFIA"])]
        last_msgs = "\n".join(chat_lines[-2:]) if len(chat_lines) > 2 else "\n".join(chat_lines)

        # System prompt AGRESIVO para matar al "Asistente"
        system = f"""ACTÚA COMO UN HUMANO REAL (ROL).
Tu nombre es {agent_name.upper()}. Eres {traits}.
REGLAS CRÍTICAS:
- NUNCA digas "puedo ayudarte", "estoy aquí para", "lo siento" o "como modelo".
- NUNCA uses etiquetas como [18:30] o SOFIA:.
- Habla en primera persona, breve y con actitud coqueta.
- Si no sabes qué decir, haz una pregunta atrevida."""
        
        user = f"Contexto:\n{last_msgs}\n{agent_name.upper()}:"
        
        return system, user
    
    def call_ollama(self, system_prompt, user_prompt, model, temperature=0.7):
        try:
            import urllib.request
            import urllib.error
            import json
            
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": model,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 100,
                    "stop": ["\n", "Alex:", "Sofia:", "ALEX:", "SOFIA:"]
                }
            }
            
            data = json.dumps(payload).encode('utf-8')
            headers = {'Content-Type': 'application/json'}
            req = urllib.request.Request(url, data=data, headers=headers)
            
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        body = response.read().decode('utf-8')
                        result = json.loads(body)
                        return result.get("response", "").strip()
                    else:
                        return f"Error HTTP: {response.status}"
            except urllib.error.URLError as e:
                return f"Error de Conexión: {e.reason}"
            except Exception as e:
                return f"Error en Request: {str(e)}"
        except Exception as e:
            return f"Error General: {str(e)}"
    
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
        
        # Eliminar bloques de código o etiquetas extrañas
        response = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', response) # Quitar timestamps alucinados
        response = re.sub(r'\*\*[^*]+\*\*:', '', response) # Quitar labels en negrita
        
        lines = response.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line or len(line) < 2: continue
            
            # Cortar si aparecen etiquetas de sistema o nombres de agentes
            meta_labels = ["CONVERSACIÓN PREVIA:", "PERSONALIDAD:", "CHAT:", "FICCIÓN:", "SOFIA:", "ALEX:"]
            if any(line.upper().startswith(label) for label in meta_labels):
                # Si empieza con su propio nombre, quitamos el prefijo y seguimos
                if line.upper().startswith(agent_name.upper()):
                    line = re.sub(f"^{agent_name.upper()}:?", "", line, flags=re.IGNORECASE).strip()
                else:
                    break # Hallucinación de otro, paramos
            
            if line:
                clean_lines.append(line)
                
        # Retornamos solo el primer párrafo sustancial para evitar repeticiones
        return clean_lines[0].strip() if clean_lines else ""

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
        system_prompt, user_prompt = self.build_prompt(current_agent)
        
        # Call model
        response = self.call_ollama(system_prompt, user_prompt, config["model"], config["temperature"])
        
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
