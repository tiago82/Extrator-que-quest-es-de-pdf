import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

import pypdfium2 as pdfium
from recorte import extract, find_pairs, load_regions, pixels, read_console_regions


def fixture_pdf(path):
    # Página com duas metades coloridas; a segunda é a mesma página girada.
    stream = b'1 0 0 rg 0 0 100 100 re f 0 0 1 rg 100 0 100 100 re f'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << >> /Contents 4 0 R >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Rotate 90 /Resources << >> /Contents 4 0 R >>',
    ]
    data = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    for offset in offsets[1:]:
        data += f'{offset:010d} 00000 n \n'.encode()
    data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode()
    path.write_bytes(data)


class ExtractorTests(unittest.TestCase):
    def test_pasted_coordinates_without_json_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            pdf = root / 'prova1.pdf'
            fixture_pdf(pdf)
            self.assertEqual(find_pairs(root), [(pdf, None)])
            data = [{'questao': '1', 'partes': [{'pagina': 1, 'coordenadas':
                    {'x0': 0, 'y0': 0, 'x1': 500, 'y1': 1000}}]}]
            lines = ['```json', *json.dumps(data, indent=2).splitlines(), '```', 'FIM']
            with patch('builtins.input', side_effect=lines):
                pasted = read_console_regions(pdf)
            output = extract(pdf, pasted, dpi=72)
            with Image.open(output / 'questao_1.png') as im:
                self.assertEqual(im.size, (100, 100))
                self.assertEqual(im.getpixel((50, 50)), (255, 0, 0))
            self.assertFalse(pdf.with_suffix('.json').exists())

    def test_retry_and_skip_console_input(self):
        with patch('builtins.input', side_effect=['not json', 'FIM', 'PULAR']):
            self.assertIsNone(read_console_regions(Path('prova1.pdf')))

    def test_entire_local_workflow_and_rotation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            pdf = root / 'fixture.pdf'
            fixture_pdf(pdf)
            data = [
                {'questao': '1', 'partes': [
                    {'pagina': 1, 'coordenadas': {'x0': 0, 'y0': 0, 'x1': 100, 'y1': 100}}]},
                {'questao': '2', 'partes': [
                    {'pagina': 1, 'coordenadas': {'x0': 0, 'y0': 0, 'x1': 100, 'y1': 100}},
                    {'pagina': 2, 'coordenadas': {'x0': 0, 'y0': 0, 'x1': 100, 'y1': 100}}]}]
            regions = root / 'fixture.json'
            regions.write_text(json.dumps(data))
            self.assertEqual(find_pairs(root), [(pdf, regions)])
            extract(pdf, regions, dpi=72, unidade='pontos')
            self.assertEqual(sorted(p.name for p in (root / 'fixture').iterdir()), ['questao_1.png', 'questao_2.png'])
            with Image.open(root / 'fixture/questao_1.png') as im:
                self.assertEqual(im.size, (100, 100))
                self.assertEqual(im.getpixel((50, 50)), (255, 0, 0))
            with Image.open(root / 'fixture/questao_2.png') as im:
                self.assertEqual(im.size, (100, 220))
                self.assertEqual(im.getpixel((50, 50)), (255, 0, 0))
                self.assertEqual(im.getpixel((50, 170)), (255, 0, 0))
                self.assertEqual(im.getpixel((50, 110)), (255, 255, 255))
            original = (root / 'fixture/questao_1.png').read_bytes()
            second = extract(pdf, regions, dpi=72, unidade='pontos')
            third = extract(pdf, regions, dpi=72, unidade='pontos')
            self.assertEqual(second, root / 'fixture (1)')
            self.assertEqual(third, root / 'fixture (2)')
            self.assertEqual((root / 'fixture/questao_1.png').read_bytes(), original)
            self.assertEqual((second / 'questao_1.png').read_bytes(), original)

    def test_rejects_invalid_regions_before_creating_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            pdf = root / 'fixture.pdf'
            fixture_pdf(pdf)
            regions = root / 'regioes.json'
            base = [{'questao': '1', 'partes': [{'pagina': 1, 'coordenadas': {}}]}]
            for box in ([0, 0, 201, 100], [100, 0, 0, 100], [0, 0, float('nan'), 100], [False, 0, 100, 100]):
                base[0]['partes'][0]['coordenadas'] = dict(zip(('x0', 'y0', 'x1', 'y1'), box))
                regions.write_text(json.dumps(base))
                with self.assertRaises(ValueError):
                    extract(pdf, regions, unidade='pontos')
                self.assertFalse((root / 'fixture').exists())
            base[0]['partes'][0]['coordenadas'] = {'x0': 0, 'y0': 0, 'x1': 100, 'y1': 100}
            base.append(base[0])
            regions.write_text(json.dumps(base))
            with self.assertRaises(ValueError):
                extract(pdf, regions, unidade='pontos')

    def test_pixel_and_normalized_coordinates(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            pdf = root / 'fixture.pdf'
            fixture_pdf(pdf)
            regions = root / 'fixture.json'
            with pdfium.PdfDocument(str(pdf)) as doc:
                for unidade, box, ref in [('pixels', [0, 0, 200, 200], 144),
                                         ('normalizada', [0, 0, 0.5, 1], 72),
                                         ('grade1000', [0, 0, 500, 1000], 72)]:
                    regions.write_text(json.dumps([{'questao': '1', 'partes': [
                        {'pagina': 1, 'coordenadas': dict(zip(('x0', 'y0', 'x1', 'y1'), box))}]}]))
                    parsed = load_regions(regions, doc, unidade, ref)
                    self.assertEqual(parsed[0]['partes'][0]['bbox'], [0, 0, 0.5, 1])

    def test_rounding_preserves_edges(self):
        self.assertEqual(pixels([0.1, 0.1, 0.9, 0.9], 11, 11), (1, 1, 10, 10))


if __name__ == '__main__':
    unittest.main()
