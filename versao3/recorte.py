"""Recorta PDFs usando um JSON existente ou coordenadas coladas no console."""
import argparse
from contextlib import closing
import json
import math
from pathlib import Path
import re
import tempfile

import pypdfium2 as pdfium
from PIL import Image


def render(page, scale):
    bitmap = page.render(scale=scale)
    try:
        return bitmap.to_pil().convert('RGB').copy()
    finally:
        bitmap.close()


def load_regions(path, doc, unidade='grade1000', dpi_referencia=72):
    data = json.loads(path.read_text(encoding='utf-8-sig')) if isinstance(path, Path) else path
    if not isinstance(data, list) or not data:
        raise ValueError('O JSON deve ser uma lista não vazia de questões.')
    sizes = {}
    ids = set()
    questions = []
    for question in data:
        ident = question.get('questao')
        if type(ident) is int:
            ident = str(ident)
        if not isinstance(ident, str) or not re.fullmatch(r'(?:[A-Za-z0-9_-]{1,80}|\d{1,3}\.\d{1,3})', ident):
            raise ValueError('questao deve ser um número, número com sufixo (78.1) ou ID com letras ASCII, números, hífen ou sublinhado.')
        if ident.lower() in ids:
            raise ValueError(f'Questão duplicada: {ident}')
        ids.add(ident.lower())
        parts = question.get('partes')
        if not isinstance(parts, list) or not parts:
            raise ValueError(f'Questão {ident}: partes deve ser uma lista não vazia.')
        validated = []
        for part in parts:
            number = part.get('pagina')
            if type(number) is not int or not 1 <= number <= len(doc):
                raise ValueError(f'Questão {ident}: página inválida: {number}.')
            if number not in sizes:
                with closing(doc[number - 1]) as page:
                    sizes[number] = page.get_size()
            coords = part.get('coordenadas')
            if not isinstance(coords, dict):
                raise ValueError(f'Questão {ident}: faltam coordenadas.')
            box = [coords.get(k) for k in ('x0', 'y0', 'x1', 'y1')]
            if not all(type(n) in (int, float) and math.isfinite(n) for n in box):
                raise ValueError(f'Questão {ident}: coordenadas devem ser números finitos.')
            width, height = sizes[number]
            if unidade == 'pixels':
                width = math.ceil(width * dpi_referencia / 72)
                height = math.ceil(height * dpi_referencia / 72)
            elif unidade == 'normalizada':
                width, height = 1, 1
            elif unidade == 'grade1000':
                width, height = 1000, 1000
            if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
                raise ValueError(f'Questão {ident}, página {number}: região invertida ou fora da página '
                                 f'({width:g} x {height:g}, unidade: {unidade}).')
            validated.append({'pagina': number, 'bbox': [box[0] / width, box[1] / height,
                                                         box[2] / width, box[3] / height]})
        questions.append({'id': ident, 'partes': validated})
    return questions


def pixels(box, width, height):
    return (math.floor(box[0] * width), math.floor(box[1] * height),
            math.ceil(box[2] * width), math.ceil(box[3] * height))


def extract(pdf, regions, dpi=200, unidade='grade1000', dpi_referencia=72, output_base=None):
    base_output = output_base or pdf.with_suffix('')
    with pdfium.PdfDocument(str(pdf)) as doc:
        questions = load_regions(regions, doc, unidade, dpi_referencia)
        suffix = 0
        while True:
            output = base_output if suffix == 0 else base_output.with_name(f'{base_output.name} ({suffix})')
            try:
                output.mkdir(exist_ok=False)
                break
            except FileExistsError:
                suffix += 1
        by_page = {}
        for qi, question in enumerate(questions):
            for pi, part in enumerate(question['partes']):
                by_page.setdefault(part['pagina'], []).append((qi, pi, part['bbox']))
        # Temporários dentro da pasta da prova, com caminho absoluto verificado.
        with tempfile.TemporaryDirectory(prefix='.partes_', dir=output.resolve()) as tmp:
            tmp = Path(tmp)
            for number, entries in sorted(by_page.items()):
                with closing(doc[number - 1]) as page:
                    im = render(page, dpi / 72)
                    try:
                        for qi, pi, box in entries:
                            crop = im.crop(pixels(box, im.width, im.height))
                            try:
                                crop.save(tmp / f'{qi}_{pi}.png')
                            finally:
                                crop.close()
                    finally:
                        im.close()
            for qi, question in enumerate(questions):
                paths = [tmp / f'{qi}_{pi}.png' for pi in range(len(question['partes']))]
                sizes = []
                for path in paths:
                    with Image.open(path) as part:
                        sizes.append(part.size)
                gap = 20 if len(paths) > 1 else 0
                canvas = Image.new('RGB', (max(w for w, h in sizes),
                                          sum(h for w, h in sizes) + gap * (len(paths) - 1)), 'white')
                try:
                    y = 0
                    for path in paths:
                        with Image.open(path) as part:
                            canvas.paste(part, (0, y))
                            y += part.height + gap
                    canvas.save(output / f"questao_{question['id']}.png")
                finally:
                    canvas.close()
    print(f'{pdf.name}: {len(questions)} imagens geradas em {output.resolve()}')
    return output


def find_pairs(entrada):
    if entrada.is_file() and entrada.suffix.lower() == '.pdf':
        pdfs = [entrada]
    elif entrada.is_dir():
        pdfs = sorted(p for p in entrada.iterdir() if p.is_file() and p.suffix.lower() == '.pdf')
    else:
        raise ValueError('Informe uma pasta ou um arquivo PDF existente.')
    pairs = []
    for pdf in pdfs:
        regions = pdf.with_suffix('.json')
        pairs.append((pdf, regions if regions.is_file() else None))
    if not pairs:
        raise ValueError('Nenhum PDF foi encontrado.')
    return pairs


def read_console_regions(pdf):
    print(f'\n{pdf.name}: não foi encontrado {pdf.with_suffix(".json").name}.')
    print('Cole as coordenadas da IA (JSON, pode ter várias linhas).')
    print('Finalize com FIM em uma linha separada e pressione Enter. Use PULAR para ignorar este PDF.')
    while True:
        lines = []
        while True:
            line = input()
            if line.strip().upper() == 'PULAR':
                return None
            if line.strip().upper() == 'FIM':
                break
            lines.append(line)
        text = '\n'.join(lines).strip().lstrip('\ufeff')
        # Aceita a cerca de Markdown que alguns chats adicionam à resposta.
        if text.startswith('```'):
            fenced = text.splitlines()
            if len(fenced) >= 3 and fenced[-1].strip() == '```':
                text = '\n'.join(fenced[1:-1])
        try:
            data = json.loads(text)
            if not isinstance(data, list) or not data:
                raise ValueError('As coordenadas devem ser uma lista não vazia de questões.')
            return data
        except ValueError as error:
            print(f'JSON inválido: {error}')
            print('Cole novamente e finalize com FIM, ou digite PULAR.')


def positive(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError('Informe um inteiro positivo.')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('entrada', type=Path, nargs='?', default=Path(__file__).resolve().parent,
                        help='Pasta com PDFs ou PDF específico; padrão: pasta deste script')
    parser.add_argument('--dpi', type=positive, default=200, help='Resolução das imagens finais')
    parser.add_argument('--unidade', choices=['grade1000', 'pontos', 'pixels', 'normalizada'], default='grade1000')
    parser.add_argument('--dpi-referencia', type=positive, default=72,
                        help='DPI da imagem sobre a qual a IA marcou pixels (somente --unidade pixels)')
    args = parser.parse_args()
    errors = 0
    try:
        pairs = find_pairs(args.entrada.resolve())
    except (ValueError, OSError) as error:
        parser.exit(1, f'Erro: {error}\n')
    for pdf, regions in pairs:
        try:
            if regions is None:
                regions = read_console_regions(pdf)
                if regions is None:
                    print(f'Ignorado: {pdf.name}.')
                    continue
            extract(pdf, regions, args.dpi, args.unidade, args.dpi_referencia)
        except (EOFError, KeyboardInterrupt):
            parser.exit(1, '\nEntrada interrompida. Execute em um console e finalize a colagem com FIM.\n')
        except (ValueError, OSError, pdfium.PdfiumError, TypeError, AttributeError) as error:
            errors += 1
            print(f'Erro em {pdf.name}: {error}')
    if errors:
        parser.exit(1, f'{errors} prova(s) com erro.\n')


if __name__ == '__main__':
    main()
