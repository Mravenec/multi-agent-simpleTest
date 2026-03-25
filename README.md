# Sistema de Cortejo Tinder - Alex & Sofia

## Estructura
```
multi-agent/
├── agents/           # Alex (chico) y Sofia (chica)
├── orchestrator/     # Controlador del cortejo
├── shared/          # Conversación y progreso
└── prompts/         # Reglas de flirteo
```

## Requisitos
- Ollama con modelo qwen2.5:0.5b

## Ejecución
```bash
cd multi-agent
./orchestrator/loop.sh
```

## Monitoreo
- Conversación: `cat shared/conversation.txt`
- Progreso: `cat shared/state.json`

## Características
- Simulación realista de cortejo
- Progresión gradual a intimidad
- Respuestas coquetas y sugestivas
- Máx 2 líneas por respuesta
