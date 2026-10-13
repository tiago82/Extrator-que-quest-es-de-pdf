"""Configuração validada dos formatos de prova usados pelo detector local."""
import json
import math
from pathlib import Path
import re


DEFAULT_PROFILE = {
    'nome': 'UECE',
    'numero_regex': r'(?P<numero>\d{2,3})\.',
    'exigir_negrito': True,
    'primeira_questao': 1,
    'ignorar_paginas_iniciais': 0,
    'colunas': 'auto',
    'inicios_colunas': None,
    'limite_superior': None,
    'limite_inferior': None,
    'margem_pontos': 3,
    'tolerancia_alinhamento': 8,
    'titulo_regex': r'^PROVA(?:[IVX]+|\d+)[-–]',
    'parada_regex': r'^RASCUNHO$',
    'quantidade_esperada': None,
}


def validate_profile(values):
    if not isinstance(values, dict):
        raise ValueError('O perfil deve ser um objeto JSON.')
    unknown = set(values) - set(DEFAULT_PROFILE)
    if unknown:
        raise ValueError('Campos desconhecidos no perfil: ' + ', '.join(sorted(unknown)))
    result = DEFAULT_PROFILE | values
    for key in ('nome', 'numero_regex', 'titulo_regex', 'parada_regex'):
        if not isinstance(result[key], str) or not result[key]:
            raise ValueError(f'Perfil: {key} deve ser texto não vazio.')
    for key in ('numero_regex', 'titulo_regex', 'parada_regex'):
        try:
            pattern = re.compile(result[key])
        except re.error as error:
            raise ValueError(f'Perfil: {key} inválido: {error}') from error
        if key == 'numero_regex' and 'numero' not in pattern.groupindex:
            raise ValueError('numero_regex precisa do grupo nomeado (?P<numero>...).')
    if type(result['exigir_negrito']) is not bool:
        raise ValueError('exigir_negrito deve ser true ou false.')
    for key, minimum in [('primeira_questao', 1), ('ignorar_paginas_iniciais', 0), ('quantidade_esperada', 1)]:
        value = result[key]
        if key == 'quantidade_esperada' and value is None:
            continue
        if type(value) is not int or value < minimum:
            raise ValueError(f'{key} deve ser inteiro >= {minimum}.')
    if result['colunas'] not in ('auto', '1', '2'):
        raise ValueError('colunas deve ser "auto", "1" ou "2".')
    for key in ('limite_superior', 'limite_inferior'):
        value = result[key]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError(f'{key} deve ser null ou uma fração entre 0 e 1.')
    if result['limite_superior'] is not None and result['limite_inferior'] is not None:
        if result['limite_superior'] >= result['limite_inferior']:
            raise ValueError('limite_superior deve ser menor que limite_inferior.')
    for key in ('margem_pontos', 'tolerancia_alinhamento'):
        value = result[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{key} deve ser um número finito não negativo.')
    starts = result['inicios_colunas']
    if starts is not None:
        if not isinstance(starts, list) or len(starts) not in (1, 2) or not all(
                type(v) in (int, float) and math.isfinite(v) and 0 < v < 1 for v in starts):
            raise ValueError('inicios_colunas deve ser null ou uma lista com uma ou duas frações entre 0 e 1.')
        if starts != sorted(set(starts)):
            raise ValueError('inicios_colunas deve conter posições distintas em ordem crescente.')
        if result['colunas'] != 'auto' and len(starts) != int(result['colunas']):
            raise ValueError('colunas e inicios_colunas não correspondem.')
    return result


def load_profile(path=None):
    if path is None:
        return validate_profile({})
    if isinstance(path, dict):
        return validate_profile(path)
    return validate_profile(json.loads(Path(path).read_text(encoding='utf-8-sig')))
