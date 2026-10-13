from pathlib import Path
import tempfile
import unittest

from extrator_v2 import detect
from perfis_v2 import load_profile


def make_pdf(path, text=True, regular=False, single_digits=False):
    stream = b''
    if text:
        stream = b'\n'.join([
            b'BT /F1 12 Tf 36 700 Td (01. PRIMEIRA) Tj ET',
            b'BT /F1 12 Tf 36 500 Td (02. SEGUNDA) Tj ET',
            b'BT /F1 12 Tf 320 750 Td (CONTINUACAO DA SEGUNDA) Tj ET',
            b'BT /F1 12 Tf 320 600 Td (03. TERCEIRA) Tj ET',
            b'BT /F1 12 Tf 320 400 Td (04. QUARTA) Tj ET',
            b'BT /F1 12 Tf 320 300 Td (RASCUNHO) Tj ET'])
    if single_digits:
        for number in range(1, 5):
            stream = stream.replace(f'0{number}.'.encode(), f'{number}\\)'.encode())
    font = b'Helvetica' if regular else b'Helvetica-Bold'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /' + font + b' >>']
    data = b'%PDF-1.4\n'
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode()
    path.write_bytes(data)


class DetectionTests(unittest.TestCase):
    def test_diagnostics_preserve_regions_and_explain_continuation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            pdf = Path(tmp) / 'teste.pdf'
            make_pdf(pdf)
            expected, _ = detect(pdf)
            diagnostic = {}
            actual, _ = detect(pdf, diagnostics=diagnostic)
            self.assertEqual(expected, actual)
            page = diagnostic['paginas'][0]
            self.assertEqual(sum(c['aceito'] for c in page['candidatos']), 4)
            self.assertEqual(len(page['colunas']), 2)
            self.assertTrue(any(r['questao']=='02' and r['tipo']=='continuação' for r in page['regioes']))
            self.assertTrue(any(m['tipo']=='stop' for m in page['marcadores']))
            self.assertTrue(all(r['caracteres']>0 for r in page['regioes']))

    def test_custom_numbering_and_nonbold_font(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            pdf = Path(tmp) / 'teste.pdf'
            make_pdf(pdf, regular=True, single_digits=True)
            with self.assertRaises(ValueError):
                detect(pdf)
            profile = {'numero_regex': r'(?P<numero>\d{1,3})[.)]', 'exigir_negrito': False,
                       'quantidade_esperada': 5, 'inicios_colunas': [36/595,320/595]}
            questions, warnings = detect(pdf, profile=profile)
            self.assertEqual([q['questao'] for q in questions], ['01','02','03','04'])
            self.assertTrue(any('esperadas 5' in w for w in warnings))
            questions, _ = detect(pdf, profile=profile | {'primeira_questao': 2})
            self.assertEqual([q['questao'] for q in questions], ['02','03','04'])

    def test_invalid_profiles_are_rejected(self):
        for value in [{'campo_errado': 1}, {'numero_regex': r'\d+'},
                      {'limite_superior': .9, 'limite_inferior': .1},
                      {'inicios_colunas': [.6,.1]}, {'exigir_negrito': 'false'}]:
            with self.assertRaises(ValueError):
                load_profile(value)

    def test_column_continuation_and_scratch_area(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            pdf = Path(tmp) / 'teste.pdf'
            make_pdf(pdf)
            questions, warnings = detect(pdf)
            self.assertEqual([q['questao'] for q in questions], ['01','02','03','04'])
            self.assertEqual(len(questions[1]['partes']), 2)
            self.assertLess(questions[1]['partes'][0]['coordenadas']['x0'], 100)
            self.assertGreater(questions[1]['partes'][1]['coordenadas']['x0'], 300)
            self.assertLess(questions[-1]['partes'][0]['coordenadas']['y1'], 540)
            self.assertFalse(any('Numeração inesperada' in w for w in warnings))

    def test_no_text_reports_need_for_ocr(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            pdf = Path(tmp) / 'teste.pdf'
            make_pdf(pdf, text=False)
            with self.assertRaisesRegex(ValueError, 'OCR'):
                detect(pdf)


if __name__ == '__main__':
    unittest.main()
