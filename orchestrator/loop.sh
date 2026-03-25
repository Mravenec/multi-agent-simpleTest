#!/bin/bash

# Loop para conversación multi-agente
echo "Iniciando loop de conversación multi-agente..."
echo "Presiona Ctrl+C para detener"

while true; do
    python3 orchestrator/orchestrator.py
    if [ $? -ne 0 ]; then
        echo "Error en el orquestador, deteniendo..."
        break
    fi
    sleep 1
done
