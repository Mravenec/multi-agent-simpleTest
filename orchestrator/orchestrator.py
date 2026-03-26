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

    def build_prompt(self, agent_name):
        conversation = self.load_conversation()
        
        # Historial real
        lines = [l.strip() for l in conversation.split('\n') if l.strip()]
        chat_lines = [l for l in lines if ":" in l and any(n in l.upper() for n in ["ALEX", "SOFIA"])]
        last_chat = "\n".join(chat_lines[-3:]) if chat_lines else ""
        
        # PROMPT DE COMPLETADO RAW
        # Sin system_prompt para que el modelo 0.5B sea puro autocompletado de chat.
        system_prompt = ""
        traits = "misteriosa y juguetona" if agent_name == "sofia" else "directo y seguro"
        user_prompt = f"{agent_name.capitalize()} es {traits} en un chat.\n\n{last_chat}\n{agent_name.capitalize()}:"
        
        return system_prompt, user_prompt
    
    def call_ollama(self, system_prompt, user_prompt, model, temperature=0.8):
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
                    "temperature": 0.4, # Menor temperatura = menos asistencialismo
                    "top_p": 0.9,
                    "top_k": 20,
                    "num_predict": 100,
                    "stop": ["\n", "\n\n", "Alex:", "Sofia:", "[", "Lo siento", "asistir"]
                }
            }
            
            data = json.dumps(payload).encode('utf-8')
            headers = {'Content-Type': 'application/json'}
            req = urllib.request.Request(url, data=data, headers=headers)
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    body = response.read().decode('utf-8')
                    result = json.loads(body)
                    return result.get("response", "").strip()
                return f"Error HTTP: {response.status}"
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
        
        # Extraer parte de (hablando)
        if "(hablando):" in response:
            response = response.split("(hablando):")[-1].strip()
        elif f"{agent_name.capitalize()}:" in response:
            response = response.split(f"{agent_name.capitalize()}:")[-1].strip()
        
        # Limpieza de pensamientos accidentales
        response = re.sub(r'\(pensando\):.*', '', response, flags=re.DOTALL)
        response = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', response)
        
        # Filtro de IA
        ai_boilerplate = ["modelo de lenguaje", "inteligencia artificial", "creado por alibaba", "qwen"]
        if any(phrase in response.lower() for phrase in ai_boilerplate):
            return "Error: IA Detectada"

        lines = [l.strip() for l in response.split('\n') if l.strip()]
        return lines[0] if lines else ""

    def switch_turn(self, current_agent):
        return "sofia" if current_agent == "alex" else "alex"

    def run_turn(self):
        state = self.load_state()
        if not state["conversation_active"] or state["iteration"] >= state["max_iterations"]:
            return False
            
        current_agent = state["current_turn"]
        print(f"Turno de: {current_agent}")
        config = self.load_agent_config(current_agent)
        
        conversation = self.load_conversation()
        lines = [l.strip() for l in conversation.split('\n') if l.strip()]
        chat_lines = [l for l in lines if ":" in l and any(n in l.upper() for n in ["ALEX", "SOFIA"])]
        
        if not chat_lines and current_agent == "alex":
            response = "Tienes una mirada en esas fotos que me dice que los viajes son lo tuyo. ¿Cuál fue el último sitio donde te perdiste?"
            state["start_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        else:
            # Dialogue Jumpstart: Pre-fill for Sofia to avoid AI reflex
            prefix = "Pues " if current_agent == "sofia" else ""
            system_prompt, user_prompt = self.build_prompt(current_agent)
            user_prompt += f" {prefix}"
            
            response_raw = self.call_ollama(system_prompt, user_prompt, config["model"], config["temperature"])
            if response_raw and not response_raw.startswith("Error:"):
                response = prefix + self.clean_response(response_raw, current_agent)
            else:
                response = response_raw
        
        if response and not response.startswith("Error:"):
            self.update_conversation(current_agent, response)
            self.update_memory(current_agent, response)
            
            state["iteration"] += 1
            state["current_turn"] = self.switch_turn(current_agent)
            state["last_response"] = response
            self.save_state(state)
            
            print(f"{current_agent}: {response}")
            return True
        else:
            print(f"Error en respuesta de {current_agent}: {response}")
            return False

if __name__ == "__main__":
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    orchestrator = MultiAgentOrchestrator(base_path)
    print("Iniciando simulación...")
    try:
        while orchestrator.run_turn():
            time.sleep(2)
    except Exception as e:
        print(f"Error final: {e}")
