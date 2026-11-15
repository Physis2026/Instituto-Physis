"""Motores de cálculo da Physis: pvlib, windpowerlib, EnergyPlus, EPANET (wntr) e SWMM (pyswmm).

Cada módulo separa duas partes:
- montar a entrada (validação + arquivo IDF/INP): só biblioteca padrão, sempre testável;
- rodar o motor: importa a biblioteca aberta só na hora (sem ela, o serviço responde 503 e o hub segue sem).
"""
__version__ = "0.1.0"
