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

    def build_prompt(self, agent_name, last_message="", chat_lines=None):
        conversation = self.load_conversation()
        # Simplificar: no cargar personalidades complejas que contaminan
        memory = self.load_agent_memory(agent_name)
        
        # Historial simple - ARREGLADO
        lines = [l.strip() for l in conversation.split('\n') if l.strip()]
        # Buscar líneas que contienen timestamps y nombres de agentes
        chat_lines = []
        for line in lines:
            if ("ALEX:" in line or "SOFIA:" in line) and "[" in line:
                chat_lines.append(line)
        
        last_chat = "\n".join(chat_lines[-1:]) if chat_lines else ""
        
        # Contexto simple
        other_agent = "sofia" if agent_name == "alex" else "alex"
        
        # Personalidad ultra simple SIN metadatos
        if agent_name == "alex":
            personality = "Soy Alex, 28 años. Me gusta el diseño y la creatividad. Soy directo y seguro."
        else:
            personality = "Soy Sofia, 26 años. Soy diseñadora. Soy misteriosa e inteligente."
        
                # Sistema ANALÍTICO con MEMORIA integrada y más contexto
        memory = self.load_agent_memory(agent_name)
        memory_text = "\n".join(memory.split('\n')[-5:])  # Últimas 5 respuestas
        
        # Más contexto de conversación
        recent_chat = "\n".join(chat_lines[-4:]) if chat_lines else ""
        
        system_prompt = f"""Eres {agent_name.capitalize()}. Hablas con {other_agent.capitalize()} en una conversación de ligue.

{personality}

TU MEMORIA RECIENTE (NO REPITAS estas frases):
{memory_text}

REGLAS OBLIGATORIAS:
- Lee y ANALIZA el último mensaje que {other_agent.capitalize()} dijo
- Responde DIRECTAMENTE a lo que dijo, no a algo genérico
- Máximo 1 línea, pero completa y relevante
- NUNCA digas tu nombre o te presentes
- Evita frases que ya dijiste antes
- Sé creativo y natural, como en una conversación real
- Si habla de diseño/trabajo, responde sobre eso específicamente
- Si pregunta algo, responde la pregunta"""

        # Few-shot con personalidad específica y más contexto
        if agent_name == "alex":
            chat_format = f"Alex: Esa foto tiene historia...\nSofia: Depende del día...\nAlex: Me intrigas con esa respuesta.\n\n"
        else:
            chat_format = f"Sofia: Esa pregunta dice más de ti que de mí...\nAlex: ¿Por qué lo dices?\nSofia: Porque revela tus intereses.\n\n"
        
        user_prompt = f"{chat_format}CONVERSACIÓN RECIENTE:\n{recent_chat}\n\nÚLTIMO MENSAJE DE {other_agent.upper()}: {last_message}\n\n{agent_name.capitalize()}:"
        
        return system_prompt, user_prompt
        
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
        
        # Limpieza PROFUNDA de metadatos de personalidad
        response = re.sub(r'##.*', '', response, flags=re.DOTALL)  # Headers
        response = re.sub(r'\*\*.*?\*\*', '', response, flags=re.DOTALL)  # Negritas
        response = re.sub(r'- \*\*.*?\*\*:', '', response, flags=re.DOTALL)  # Listas con negrita
        response = re.sub(r'- .*', '', response, flags=re.DOTALL)  # Todas las listas
        response = re.sub(r'\[.*?\]', '', response, flags=re.DOTALL)  # Corchetes
        response = re.sub(r'Tono:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Ritmo:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Temas favoritos:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Evito:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Señales de Interés:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Prohibido Absolutamente:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Ejemplos de mi Voz:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Lo que busco en.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Dinámica Relacional:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Fondo Personal:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Esencia:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Deseos Profundos:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Miedos y Vulnerabilidades:.*', '', response, flags=re.DOTALL)
        response = re.sub(r'Estilo de Comunicación:.*', '', response, flags=re.DOTALL)
        
        # Eliminar timestamps y etiquetas
        response = re.sub(r'\(pensando\):.*', '', response, flags=re.DOTALL)
        response = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', response)
        response = re.sub(r'\[\d{4}-\d{2}-\d{2}.*?\]', '', response, flags=re.DOTALL)
        
        # Limpiar caracteres extraños y espacios múltiples
        response = re.sub(r'\s+', ' ', response).strip()
        
        # Filtro de errores de identidad
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
        print(f"\n{'='*50}")
        print(f" TURNO DE: {current_agent.upper()} (Iteración {state['iteration'] + 1})")
        print(f"{'='*50}")
        
        config = self.load_agent_config(current_agent)
        
        conversation = self.load_conversation()
        # Extraer mensajes correctamente - PARSING COMPLETO
        lines = [l.strip() for l in conversation.split('\n') if l.strip()]
        chat_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if ("ALEX:" in line or "SOFIA:" in line) and "[" in line:
                # Esta línea tiene el timestamp y agente
                message_lines = [line]
                # Siguiente línea puede tener el mensaje
                if i + 1 < len(lines) and not lines[i + 1].startswith("["):
                    message_lines.append(lines[i + 1])
                    i += 1  # Saltar la siguiente línea ya que la procesamos
                chat_lines.append('\n'.join(message_lines))
            i += 1
        
        print(f" CONTEXTO ACTUAL:")
        if chat_lines:
            last_messages = chat_lines[-2:]
            for msg in last_messages:
                print(f"   {msg}")
        else:
            print("   (Inicio de conversación)")
        
        print(f"\n PROCESO DE PENSAMIENTO DE {current_agent.upper()}:")
        
        if not chat_lines and current_agent == "alex":
            response = "Hola Sofia, vi tu perfil de diseñadora. ¿Qué tipo de proyectos te apasionan más?"
            state["start_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            print(f"   Alex: 'Iniciaré conversación sobre diseño de forma simple'")
        else:
            # Obtener último mensaje para contexto - EXTRACCIÓN COMPLETA
            last_message = ""
            if chat_lines:
                last_line = chat_lines[-1]
                print(f"   🔍 Línea completa: '{last_line}'")
                
                # Nuevo formato: [timestamp] AGENT:\nmensaje
                lines_in_entry = last_line.split('\n')
                if len(lines_in_entry) >= 2:
                    # Primera línea: [timestamp] AGENT:
                    # Segunda línea: mensaje
                    message_part = lines_in_entry[1].strip()
                    last_message = message_part
                    print(f"   ✅ Extraído correctamente: '{last_message}'")
                elif ": " in last_line:
                    # Fallback: mensaje en la misma línea
                    parts = last_line.split(": ", 1)
                    if len(parts) == 2:
                        last_message = parts[1].strip()
                        print(f"   ✅ Extraído (fallback): '{last_message}'")
                    else:
                        print(f"   ❌ Formato inesperado en línea")
                else:
                    print(f"   ❌ No se pudo extraer mensaje")
            else:
                print(f"   ⚠️ No hay mensajes previos")
            
            print(f"   📝 Analizando último mensaje: '{last_message}'")
            print(f"   🎯 Cargando personalidad y memoria...")
            
            # Sistema LIBRE - sin prefijos determinados
            system_prompt, user_prompt = self.build_prompt(current_agent)
            
            print(f"   🤖 Generando respuesta libre...")
            response_raw = self.call_ollama(system_prompt, user_prompt, config["model"])
            
            if response_raw and not response_raw.startswith("Error:"):
                clean = self.clean_response(response_raw, current_agent)
                if not clean.startswith("Error:") and len(clean) > 5:
                    response = clean
                    print(f"   ✅ Respuesta generada libremente")
                else:
                    # Fallback simple sin prefijos
                    memory = self.load_agent_memory(current_agent)
                    memory_lines = [l.strip() for l in memory.split('\n') if l.strip() and not l.startswith('#')]
                    
                    fallback_options = []
                    if current_agent == "alex":
                        fallback_options = [
                            "Me gusta lo que dices sobre diseño.",
                            "¿Qué te inspira en tus proyectos?",
                            "Háblame más de tu trabajo creativo."
                        ]
                    else:
                        fallback_options = [
                            "Es interesante tu perspectiva.",
                            "Depende del contexto...",
                            "¿Qué más quieres saber?"
                        ]
                    
                    # Elegir fallback que no esté en memoria reciente
                    for fallback in fallback_options:
                        if fallback not in '\n'.join(memory_lines[-3:]):
                            response = fallback
                            print(f"   🔄 Fallback único: '{response}'")
                            break
                    else:
                        response = fallback_options[0]
                        print(f"   ⚠️ Último recurso: '{response}'")
            else:
                response = "Interesante conversación..."
                print(f"   🚨 Error en Ollama, respuesta básica")
        
        if response and not response.startswith("Error:"):
            print(f"\n RESPUESTA FINAL DE {current_agent.upper()}:")
            print(f"   '{response}'")
            
            self.update_conversation(current_agent, response)
            self.update_memory(current_agent, response)
            
            state["iteration"] += 1
            state["current_turn"] = self.switch_turn(current_agent)
            state["last_response"] = response
            self.save_state(state)
            
            print(f"   Memoria actualizada")
            print(f"   Siguiente turno: {state['current_turn']}")
            print(f"   Iteración: {state['iteration']}/{state['max_iterations']}")
            
            return True
        else:
            print(f"\n ERROR EN RESPUESTA DE {current_agent.upper()}: {response}")
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
