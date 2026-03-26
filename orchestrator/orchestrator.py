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
        personality = self.load_agent_personality(agent_name)
        memory = self.load_agent_memory(agent_name)
        
        # Historial real mejorado - más contexto
        lines = [l.strip() for l in conversation.split('\n') if l.strip()]
        chat_lines = [l for l in lines if ":" in l and any(n in l.upper() for n in ["ALEX", "SOFIA"])]
        last_chat = "\n".join(chat_lines[-3:]) if chat_lines else ""
        
        # Contexto claro de quién es quién
        other_agent = "sofia" if agent_name == "alex" else "alex"
        
        # ANCLA DE IDIOMA Y ROL con identidad clara y memoria
        system_prompt = f"""Eres {agent_name.capitalize()}. Estás hablando con {other_agent.capitalize()}.
Hablas ESPAÑOL natural. No eres un asistente. Eres una persona real.

{personality}

MEMORIA CONTEXTUAL:
{memory}

REGLAS ESTRICTAS:
- NUNCA saludes (hola, cómo estás, buen día)
- NUNCA te refieras a ti mismo por tu nombre
- Siempre responde DIRECTAMENTE al último mensaje de {other_agent.capitalize()}
- Máximo 2 líneas por respuesta
- Usa tu voz única según tu perfil
- NUNCA repitas la misma respuesta
- EVITA patrones repetitivos"""
        
        # Few-shot con personalidad específica
        if agent_name == "alex":
            chat_format = "Alex: Esa foto tiene historia...\nSofia: Depende del día...\n\n"
        else:
            chat_format = "Alex: Me intrigas...\nSofia: ¿Y tú qué crees?\n\n"
        user_prompt = f"{chat_format}{last_chat}\n{agent_name.capitalize()}:"
        
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
                    "temperature": 0.4, # Estabilidad
                    "top_p": 0.9,
                    "top_k": 20,
                    "num_predict": 100,
                    "stop": ["\n", "Alex:", "Sofia:", "assist", "help", "Today"]
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
        
        # Eliminar etiquetas de monólogo si quedaron
        response = re.sub(r'\(pensando\):.*', '', response, flags=re.DOTALL)
        response = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', response)
        
        # Eliminar metadatos y ejemplos contaminantes
        response = re.sub(r'- \*\*Ejemplos\*\*:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'ALEX:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'SOFIA:.*', '', response, flags=re.DOTALL)
        
        # Filtro de errores de identidad (muy importante)
        self_referencing_patterns = [
            f"{agent_name.capitalize()}", f"soy {agent_name}", f"soy un",
            "soy una", "como asistente", "modelo de lenguaje"
        ]
        
        response_lower = response.lower()
        if any(pattern.lower() in response_lower for pattern in self_referencing_patterns):
            return "Error: Identidad incorrecta."
        
        # Filtro de saludos y respuestas genéricas
        forbidden_patterns = [
            "hola", "¿cómo estás", "cómo estas", "buen día", "buenos días",
            "¿qué tal", "que tal", "¿qué hay", "que hay", "espero que estés",
            "espero que estas", "¿cómo te va", "cómo te va", "¿cómo te sientes"
        ]
        
        if any(pattern in response_lower for pattern in forbidden_patterns):
            return "Error: Saludo genérico."
        
        # Filtro de IA y Asistencialismo
        ai_boilerplate = [
            "inteligencia artificial", "qwen", "alibaba",
            "assist you", "help you", "today", "lo siento", "puedo ayudar"
        ]
        if any(phrase in response_lower for phrase in ai_boilerplate):
            return "Error: Respuesta contaminada."

        # Validar que sea una respuesta real
        lines = [l.strip() for l in response.split('\n') if l.strip()]
        if not lines:
            return "Error: Sin contenido."
        
        first_line = lines[0].strip()
        if len(first_line) < 5 or len(first_line) > 100:
            return "Error: Longitud inválida."
            
        return first_line

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
            # Obtener último mensaje para contexto
            last_message = ""
            if chat_lines:
                last_line = chat_lines[-1]
                if ":" in last_line:
                    last_message = last_line.split(":", 1)[1].strip()
            
            # Prefijos contextuales según personalidad
            if current_agent == "alex":
                if "viajes" in last_message.lower() or "foto" in last_message.lower():
                    prefixes = ["Esa foto...", "Me intriga ese lugar...", "No eres como...", "A ver, "]
                else:
                    prefixes = ["Me intriga...", "No eres como...", "A ver, ", "Pues ", "La verdad "]
            else:  # sofia
                if "viajes" in last_message.lower() or "foto" in last_message.lower():
                    prefixes = ["Depende del viaje...", "¿Y tú qué crees?", "Esa pregunta...", "Bueno, "]
                else:
                    prefixes = ["Depende...", "¿Y tú qué crees?", "Esa pregunta...", "Bueno, ", "A ver, "]
            
            response = "Error: Sin respuesta."
            
            for prefix in prefixes:
                system_prompt, user_prompt = self.build_prompt(current_agent)
                user_prompt += f" {prefix}"
                
                response_raw = self.call_ollama(system_prompt, user_prompt, config["model"])
                if response_raw and not response_raw.startswith("Error:"):
                    clean = self.clean_response(response_raw, current_agent)
                    if not clean.startswith("Error:") and len(clean) > 5:
                        response = prefix + clean
                        break
            
            # FALLBACK: Respuestas predefinidas si todo falla
            if response.startswith("Error:"):
                # Cargar respuestas anteriores para evitar repeticiones
                memory = self.load_agent_memory(current_agent)
                
                if current_agent == "sofia":
                    if "viajes" in last_message.lower() or "perdiste" in last_message.lower():
                        fallback_responses = [
                            "Depende del momento... ¿Y tú qué crees que encontré?",
                            "Esa pregunta dice más de ti que de mí...",
                            "Quizás algún día te lo cuente..."
                        ]
                    else:
                        fallback_responses = [
                            "Esa pregunta dice más de ti que de mí...",
                            "Depende del día y la compañía...",
                            "¿Y tú qué crees que debería responder?"
                        ]
                else:  # alex
                    fallback_responses = [
                        "Me intriga tu respuesta...",
                        "No eres como las demás...",
                        "Esa foto tiene historia...",
                        "Hay algo en tu forma de hablar..."
                    ]
                
                # Elegir respuesta que no esté en la memoria
                for fallback in fallback_responses:
                    if fallback not in memory:
                        response = fallback
                        break
                else:
                    response = fallback_responses[0]  # Último recurso
            
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
