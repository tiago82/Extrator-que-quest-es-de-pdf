"""Versão experimental: detecta questões localmente pela posição do texto."""
import argparse
import json
from pathlib import Path
import re
from statistics import median

import pdfplumber
import pypdfium2 as pdfium

from recorte import extract, find_pairs, positive
from perfis_v3 import load_profile
from revisao_v3 import generate_review


def page_limits(page, profile, diagnostic=None):
    rules = [r for r in page.rects + page.lines
             if r['x1'] - r['x0'] > page.width * .75 and r['bottom'] - r['top'] < 2]
    top = max((r['bottom'] for r in rules if r['top'] < page.height * .15), default=page.height * .065)
    bottom = min((r['top'] for r in rules if r['top'] > page.height * .8), default=page.height * .925)
    top = top + 2 if profile['limite_superior'] is None else profile['limite_superior'] * page.height
    bottom = bottom - .2 if profile['limite_inferior'] is None else profile['limite_inferior'] * page.height
    if top >= bottom:
        raise ValueError('Limites úteis da página invertidos; ajuste o perfil.')
    if diagnostic is not None:
        diagnostic.update({'topo': top, 'base': bottom,
            'origem_topo': 'perfil' if profile['limite_superior'] is not None else
                ('linha horizontal' if any(r['top'] < page.height * .15 for r in rules) else 'aproximação 6,5%'),
            'origem_base': 'perfil' if profile['limite_inferior'] is not None else
                ('linha horizontal' if any(r['top'] > page.height * .8 for r in rules) else 'aproximação 92,5%')})
    return top, bottom


def number_words(page, profile, audit=None):
    result = []
    all_words = page.extract_words(extra_attrs=['fontname'])
    for word in all_words:
        match = re.fullmatch(profile['numero_regex'], word['text'])
        if match and profile['prefixo_numero_regex'] is not None:
            prefixes = [w for w in all_words
                        if re.fullmatch(profile['prefixo_numero_regex'], w['text'], flags=re.IGNORECASE)
                        and abs(w['top'] - word['top']) <= 3
                        and 0 <= word['x0'] - w['x1'] <= 15]
            if not prefixes:
                continue
            prefix = max(prefixes, key=lambda w: w['x1'])
            word = word | {'text': prefix['text'] + ' ' + word['text'],
                           'x0': prefix['x0'], 'top': min(prefix['top'],word['top']),
                           'bottom': max(prefix['bottom'],word['bottom'])}
        if match and audit is not None:
            bold_ok = not profile['exigir_negrito'] or 'bold' in word['fontname'].lower()
            audit.append({'texto': word['text'], 'fonte': word['fontname'],
                          'bbox': [word['x0'],word['top'],word['x1'],word['bottom']],
                          'aceito': False, 'motivo': 'fora do alinhamento/área útil' if bold_ok else 'fonte não atende exigir_negrito'})
        if match and (not profile['exigir_negrito'] or 'bold' in word['fontname'].lower()):
            try:
                number = int(match.group('numero'))
            except (TypeError, ValueError) as error:
                raise ValueError('O grupo numero do perfil deve capturar somente dígitos.') from error
            result.append(word | {'numero': number})
    return result


def column_starts(candidates):
    clusters = []
    for x in sorted(w['x0'] for w in candidates):
        if clusters and abs(x - median(clusters[-1])) < 12:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [median(c) for c in clusters if len(c) >= 2]


def content_box(page, left, top, right, bottom, margin=3, diagnostic=None):
    if bottom <= top:
        return None
    objects = [c for c in page.chars if c['text'].strip()]
    objects += page.images + page.rects + page.curves + page.lines
    included = [o for o in objects if o['x0'] >= left - 1 and o['x1'] <= right + 1
                and o['top'] >= top - .5 and o['top'] < bottom
                and o['bottom'] > o['top'] and o['x1'] > o['x0']]
    # Somente linhas decorativas não contam como conteúdo.
    if not any(c['text'].strip() and left <= c['x0'] < right and top <= c['top'] < bottom
               for c in page.chars) and not any(o in included for o in page.images):
        return None
    if not included:
        return None
    if diagnostic is not None:
        diagnostic['bbox_conteudo'] = [min(o['x0'] for o in included), min(o['top'] for o in included),
                                      max(o['x1'] for o in included), max(o['bottom'] for o in included)]
        diagnostic['caracteres'] = sum(o['object_type'] == 'char' for o in included)
        diagnostic['graficos'] = [{'tipo': o['object_type'], 'bbox': [o['x0'],o['top'],o['x1'],o['bottom']]}
                                  for o in included if o['object_type'] != 'char']
    return [max(left, min(o['x0'] for o in included) - margin),
            max(top, min(o['top'] for o in included) - margin),
            min(right, max(o['x1'] for o in included) + margin),
            min(bottom, max(o['bottom'] for o in included) + margin)]


def detect(pdf, columns=None, profile=None, diagnostics=None):
    profile = load_profile(profile)
    columns = columns or profile['colunas']
    questions = []
    warnings = []
    active = None
    support = []
    pending = False
    previous_number = None
    with pdfplumber.open(pdf) as doc:
        if not any(page.chars for page in doc.pages):
            raise ValueError('Não há texto com posições. PDF escaneado exige OCR, não incluído na V3.')
        page_diagnostics = [{'pagina': i + 1, 'largura': p.width, 'altura': p.height,
                             'processada': False, 'candidatos': [], 'colunas': [],
                             'limites': {}, 'marcadores': [], 'regioes': []} for i,p in enumerate(doc.pages)]
        candidates = [number_words(page, profile, page_diagnostics[i]['candidatos']) for i,page in enumerate(doc.pages)]
        first = next((i for i, words in enumerate(candidates)
                      if i >= profile['ignorar_paginas_iniciais'] and
                      any(w['numero'] == profile['primeira_questao'] for w in words)), None)
        if first is None:
            raise ValueError(f"Não encontrei a primeira questão ({profile['primeira_questao']}). Confira a numeração, o negrito e as páginas ignoradas no perfil.")
        reference_width = doc.pages[first].width
        first_anchor = next(w for w in candidates[first] if w['numero'] == profile['primeira_questao'])
        seed = first_anchor['x0']
        # Aprende os alinhamentos somente a partir da primeira página de questões.
        normalized = [w | {'x0': w['x0'] * reference_width / doc.pages[i].width}
                      for i in range(first, len(doc.pages)) for w in candidates[i]]
        inferred = column_starts(normalized)
        starts = [seed] + [x for x in inferred if x > seed + reference_width * .25]
        if profile['inicios_colunas'] is not None:
            starts = [x * reference_width for x in profile['inicios_colunas']]
        if columns == '1':
            starts = [min(starts)]
        elif columns == '2' and len(starts) < 2:
            starts = [min(starts), reference_width / 2 + min(starts)]
            warnings.append('Segunda coluna estimada pela metade da largura; confira ou configure inicios_colunas.')
        starts = starts[:2]
        for pd in page_diagnostics[:first]:
            for candidate in pd['candidatos']:
                candidate['motivo'] = 'página anterior ao início detectado/configurado'
        if diagnostics is not None:
            diagnostics.update({'versao': 1, 'perfil': profile, 'primeira_pagina': first + 1,
                                'paginas': page_diagnostics, 'avisos': warnings})
        for index in range(first, len(doc.pages)):
            page = doc.pages[index]
            diagnostic = page_diagnostics[index]
            diagnostic['processada'] = True
            top, bottom = page_limits(page, profile, diagnostic['limites'])
            scaled = [s * page.width / reference_width for s in starts]
            layout_reason = None
            if len(scaled) == 2 and profile['detectar_pagina_uma_coluna']:
                anchors = [w for w in candidates[index] if top <= w['top'] < bottom]
                left_anchors = [w for w in anchors if abs(w['x0'] - scaled[0]) <= profile['tolerancia_alinhamento']]
                right_anchors = [w for w in anchors if abs(w['x0'] - scaled[1]) <= profile['tolerancia_alinhamento']]
                long_rules = [r for r in page.lines + page.rects
                              if r['x1'] - r['x0'] > .75 * page.width and r['bottom'] - r['top'] < 2
                              and any(w['top'] - 2 <= r['top'] <= w['bottom'] + 10 for w in left_anchors)]
                if left_anchors and not right_anchors and long_rules:
                    scaled = scaled[:1]
                    layout_reason = 'Uma coluna: rótulo de questão com linha larga abaixo e ausência de rótulos à direita.'
                    diagnostic['layout_adaptado'] = layout_reason
                    warnings.append(f'Página {index + 1}: detectada largura inteira pela linha do rótulo de questão.')
            for candidate in diagnostic['candidatos']:
                if candidate['motivo'].startswith('fonte'):
                    continue
                if not top <= candidate['bbox'][1] < bottom:
                    candidate['motivo'] = 'fora da área útil: cabeçalho ou rodapé'
                elif min(abs(candidate['bbox'][0] - x) for x in scaled) > profile['tolerancia_alinhamento']:
                    candidate['motivo'] = 'fora da tolerância de alinhamento das colunas'
                elif index == first and candidate['bbox'][1] < first_anchor['top'] - .5:
                    candidate['motivo'] = 'antes da primeira questão configurada'
            edges = [max(0, scaled[0] - 5)]
            if len(scaled) == 2:
                edges.append(scaled[1] - 12)
            edges.append(page.width - edges[0])
            for col in range(len(scaled)):
                left, right = edges[col], edges[col + 1]
                diagnostic['colunas'].append({'coluna': col + 1, 'esquerda': left, 'direita': right,
                    'inicio': scaled[col], 'tolerancia': profile['tolerancia_alinhamento'],
                    'origem': layout_reason or ('perfil' if profile['inicios_colunas'] is not None else 'inferência/primeira questão')})
                words = [w for w in candidates[index] if abs(w['x0'] - scaled[col]) <= profile['tolerancia_alinhamento']
                         and top <= w['top'] < bottom
                         and not (index == first and col == 0 and w['top'] < first_anchor['top'] - .5)]
                for candidate in diagnostic['candidatos']:
                    if any(w['text'] == candidate['texto'] and abs(w['top'] - candidate['bbox'][1]) < .01
                           and abs(w['x0'] - candidate['bbox'][0]) < .01 for w in words):
                        candidate.update({'aceito': True, 'motivo': 'padrão, fonte, área útil e alinhamento atendidos', 'coluna': col + 1})
                markers = [(max(top, w['top'] - profile['recuo_inicio_pontos']), 'question', w) for w in words]
                cropped = page.crop((left, top, right, bottom))
                for line in cropped.extract_text_lines():
                    compact = re.sub(r'\s+', '', line['text']).upper()
                    if re.search(profile['parada_regex'], compact):
                        markers.append((line['top'] - 3, 'stop', line))
                    elif re.search(profile['titulo_regex'], compact):
                        markers.append((line['top'] - 5, 'section', line))
                markers.sort(key=lambda item: item[0])
                diagnostic['marcadores'].extend({'tipo': kind, 'texto': item['text'], 'coluna': col + 1,
                    'y_divisao': y, 'bbox': [item['x0'],item['top'],item['x1'],item['bottom']]}
                    for y,kind,item in markers if kind != 'question')
                position = top
                origin = 'continuação'

                def add_region(y0, y1):
                    details = {}
                    box = content_box(page, left, y0, right, y1, profile['margem_pontos'], details)
                    if box is None:
                        return
                    part = {'pagina': index + 1, 'coordenadas': dict(zip(('x0', 'y0', 'x1', 'y1'), box))}
                    if pending:
                        support.append(part)
                    elif active is not None:
                        active['partes'].append(part)
                    if pending or active is not None:
                        diagnostic['regioes'].append(details | {'bbox': box, 'coluna': col + 1,
                            'questao': None if pending else active['questao'], 'tipo': 'apoio' if pending else origin,
                            'faixa_busca': [left,y0,right,y1], 'margem_pontos': profile['margem_pontos']})

                for y, kind, item in markers:
                    add_region(position, y)
                    if kind == 'question':
                        number = item['numero']
                        repeated = any(q['questao'] == f'{number:02d}' for q in questions)
                        if previous_number is not None and number != previous_number + 1:
                            if repeated and profile['numerar_repetidas'] != 'nao_tratar':
                                warnings.append(f'Reinício de numeração tratado: {number:02d} na página {index + 1}; números repetidos recebem sufixos .1, .2 etc.')
                            else:
                                warnings.append(f'Numeração inesperada: {number:02d} na página {index + 1}. Confira a revisão.')
                        previous_number = number
                        ident = f'{number:02d}'
                        if profile['numerar_repetidas'] == 'nao_tratar' and repeated:
                            raise ValueError(f'Número duplicado {ident}. O tratamento de reinício está desativado; selecione Tratar ou Automático no perfil.')
                        active = {'questao': ident, 'partes': list(support)}
                        for pd in page_diagnostics:
                            for region in pd['regioes']:
                                if region['tipo'] == 'apoio' and region['questao'] is None:
                                    region['questao'] = ident
                        support.clear()
                        questions.append(active)
                        pending = False
                        position = y
                        origin = 'início'
                    elif kind == 'section':
                        active = None
                        support.clear()
                        pending = True
                        position = item['bottom'] + .2
                    else:
                        active = None
                        pending = False
                        support.clear()
                        position = item['bottom'] + 3
                add_region(position, bottom)
        if profile['numerar_repetidas'] != 'nao_tratar':
            totals = {}
            occurrences = {}
            for question in questions:
                ident = question['questao']
                totals[ident] = totals.get(ident, 0) + 1
            for question in questions:
                ident = question['questao']
                if totals[ident] > 1:
                    occurrences[ident] = occurrences.get(ident, 0) + 1
                    question['questao'] = f'{ident}.{occurrences[ident]}'
            # As regiões estão na mesma ordem dos fragmentos das questões.
            # Identifique pelo par página/caixa para preservar a revisão dos reinícios.
            labels = {(part['pagina'], tuple(part['coordenadas'].values())): question['questao']
                      for question in questions for part in question['partes']}
            for pd in page_diagnostics:
                for region in pd['regioes']:
                    region['questao'] = labels.get((pd['pagina'], tuple(region['bbox'])), region['questao'])
        if not questions or any(not q['partes'] for q in questions):
            raise ValueError('Detecção incompleta: há questões sem conteúdo.')
        if profile['quantidade_esperada'] is not None and len(questions) != profile['quantidade_esperada']:
            warnings.append(f"ATENÇÃO: esperadas {profile['quantidade_esperada']} questões, detectadas {len(questions)}.")
        warnings.append('Heurística experimental: revise os limites e a associação de textos/tabelas compartilhados.')
        return questions, warnings


def run(pdf, dpi=200, columns=None, destination=None, profile=None):
    profile = load_profile(profile)
    if columns is not None:
        profile = load_profile(profile | {'colunas': columns})
    diagnostics = {}
    questions, warnings = detect(pdf, profile=profile, diagnostics=diagnostics)
    # Mantém o PDF original e todos os resultados da V1. Saída exclusiva da V3.
    base = (destination or Path(__file__).resolve().parent / 'saidas') / (pdf.stem + '_v3')
    base.parent.mkdir(parents=True, exist_ok=True)
    output = extract(pdf, questions, dpi=dpi, unidade='pontos', output_base=base)
    (output / 'coordenadas_v3.json').write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'avisos.txt').write_text('\n'.join(warnings), encoding='utf-8')
    (output / 'perfil_usado.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    generate_review(pdf, output, diagnostics)
    print(f'V3: {len(questions)} questões em {output.resolve()}')
    for warning in warnings:
        print(warning)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('entrada', nargs='?', type=Path, default=Path(__file__).resolve().parent / 'entradas',
                        help='PDF ou pasta de PDFs; padrão: entradas/ dentro da V3')
    parser.add_argument('--dpi', type=positive, default=200)
    parser.add_argument('--colunas', choices=['auto','1','2'], default=None, help='Sobrescreve as colunas do perfil')
    parser.add_argument('--perfil', type=Path, help='JSON com regras de detecção; padrão: regras UECE')
    parser.add_argument('--saida', type=Path, help='Pasta onde criar os resultados; padrão: saidas/ dentro da V3')
    args = parser.parse_args()
    try:
        profile = load_profile(args.perfil)
        pairs = find_pairs(args.entrada.resolve())
    except (ValueError, OSError) as error:
        parser.exit(1, f'Erro: {error}\n')
    failed = False
    for pdf, _ in pairs:
        try:
            run(pdf, args.dpi, args.colunas, args.saida, profile)
        except (ValueError, OSError, pdfium.PdfiumError) as error:
            failed = True
            print(f'Erro em {pdf.name}: {error}')
    if failed:
        parser.exit(1)


if __name__ == '__main__':
    main()
