"""Editor web local de perfis da V3. Execute: python gerador_perfis.py."""
import argparse
from contextlib import closing
import io
import json
from pathlib import Path
import re
import secrets
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser

ROOT = Path(__file__).resolve().parent
V3 = ROOT / 'versao3'
sys.path.insert(0, str(V3))
from perfis_v3 import DEFAULT_PROFILE, load_profile

# Estes modelos geram regras; todos os campos continuam editáveis.
MODELS = {
    '01. ou 1.': {'numero_regex': r'(?P<numero>\d{1,3})\.', 'prefixo_numero_regex': None},
    '01) ou 1)': {'numero_regex': r'(?P<numero>\d{1,3})\)', 'prefixo_numero_regex': None},
    'QUESTÃO 01': {'numero_regex': r'(?P<numero>\d{1,3})', 'prefixo_numero_regex': r'QUEST[ÃA]O'},
    'Q01': {'numero_regex': r'Q(?P<numero>\d{1,3})', 'prefixo_numero_regex': None},
}

PAGE = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Editor de perfis V3</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#edf2f7;color:#17283d;font:15px system-ui}
header{background:#173b50;color:white;padding:22px 30px}h1{font-size:25px;margin:0 0 7px}p{line-height:1.5}
main{display:grid;grid-template-columns:380px minmax(0,1fr);gap:20px;padding:22px;max-width:1600px;margin:auto}
aside,.card{background:white;border:1px solid #d7e0e8;border-radius:12px;padding:20px}aside{align-self:start}
h2{font-size:18px;margin-top:0}label{display:block;margin:12px 0;font-size:14px}input,select,button{font:inherit}
input:not([type=checkbox]),select{width:100%;padding:8px;border:1px solid #aebdcc;border-radius:5px;margin-top:5px}
button{border:0;border-radius:6px;padding:10px 14px;background:#147d78;color:white;cursor:pointer;margin:4px 4px 4px 0}
button.secondary{background:#e5edf3;color:#173b50}button:disabled{opacity:.5;cursor:wait}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.hint{font-size:13px;color:#52677b}details{margin:16px 0}
summary{cursor:pointer;font-weight:600}#status{white-space:pre-wrap;padding:12px;border-radius:6px;background:#e8f3f1;margin:15px 0}
#status.error{background:#ffeded;color:#9b2525}#canvas svg{width:100%;max-height:none;display:block}
#canvas{overflow:auto;background:#e5eaf0;min-height:160px}pre{white-space:pre-wrap;overflow-wrap:anywhere}
.legend{font-size:13px;margin:10px 0;color:#52677b}.checks{display:flex;flex-wrap:wrap;gap:12px}.checks label{margin:5px 0}
g[data-info]{cursor:pointer}g[data-info]:hover rect{stroke-width:2.5}.objetos{display:none}
a{color:#147d78}@media(max-width:900px){main{grid-template-columns:1fr}header{padding:20px}}
</style></head><body><header><h1>Editor de perfis de questões</h1>
<div>Ajuste as regras, confira a detecção no PDF e salve para reutilizar. Processamento local, sem IA.</div></header>
<main><aside><h2>1. Escolha o perfil</h2><select id="profileList"></select>
<button id="load" class="secondary">Carregar</button><button id="new" class="secondary">Novo perfil</button>
<form id="form"><div id="basic"></div><label>Modelo de numeração<select id="model"><option value="">Personalizado / manter atual</option></select></label>
<details><summary>Configurações avançadas</summary><p class="hint">Posições usam frações da página (0 a 1). Medidas de margem e tolerância usam pontos do PDF.</p><div id="advanced"></div></details></form>
<label>Nome do arquivo do perfil<input id="filename" value="meu_perfil.json" placeholder="minha_banca.json"></label>
<button id="save">Salvar perfil</button><button id="download" class="secondary">Baixar JSON</button>
<p class="hint">Salva em versao3/perfis. Para substituir um arquivo existente, confirme na janela de aviso.</p>
</aside><div><div class="card"><h2>2. Abra um PDF e teste</h2>
<label>Escolher PDF do computador<input id="upload" type="file" accept=".pdf,application/pdf"></label>
<details><summary>Usar caminho completo do PDF</summary><label>Caminho<input id="pdfPath" placeholder="C:\Provas\prova.pdf"></label><button id="openPath" class="secondary">Abrir caminho</button></details>
<p id="pdfInfo" class="hint">Nenhum PDF aberto.</p><button id="test">Testar perfil</button>
<button id="extract" class="secondary">Gerar imagens das questões</button>
<div id="status" role="status">Carregue um perfil e abra um PDF para começar.</div><div id="output"></div>
</div><div class="card" style="margin-top:20px"><h2>3. Confira as marcações</h2>
<div class="row"><label>Página<select id="page"></select></label><label>Aplicar posição ao clicar<select id="pick">
<option value="">Consultar marcações</option><option value="limite_superior">Limite superior</option><option value="limite_inferior">Limite inferior</option>
<option value="coluna1">Início da coluna 1</option><option value="coluna2">Início da coluna 2</option></select></label></div>
<p class="hint">Selecione um ajuste e clique na página para preencher sua posição. Clique em Testar perfil para recalcular.</p>
<div class="checks" id="layers"></div><p class="legend">Verde: número aceito · vermelho: rejeitado · azul: início · laranja: continuação · roxo: apoio · ciano: alinhamento</p>
<div id="canvas"></div><pre id="info">Clique em uma marcação para consultar o motivo.</pre>
</div></div></main><script>
const TOKEN=__TOKEN__;let defaults={},models={},pdfId=null,activePage=null;
const $=id=>document.getElementById(id);
const fields=[
['nome','Nome do perfil','text',0],['colunas','Colunas','select',0],
['primeira_questao','Número da primeira questão','int',0],['quantidade_esperada','Total esperado (vazio = sem conferência)','int?',0],
['ignorar_paginas_iniciais','Páginas iniciais a ignorar','int',0],['exigir_negrito','Exigir numeração em negrito','bool',0],
['limite_superior','Limite superior (vazio = automático)','float?',0],['limite_inferior','Limite inferior (vazio = automático)','float?',0],
['numero_regex','Padrão do número (regex)','text',1],['prefixo_numero_regex','Prefixo do número (vazio = nenhum)','text?',1],
['numerar_repetidas','Reinício de numeração','repeat-select',0],
['inicios_colunas','Inícios das colunas: ex. 0.06, 0.54','array?',1],
['detectar_pagina_uma_coluna','Adaptar páginas de largura inteira pela regra da V3','bool',1],
['margem_pontos','Margem do conteúdo (pontos)','float',1],['recuo_inicio_pontos','Recuo acima do número (pontos)','float',1],
['tolerancia_alinhamento','Tolerância de alinhamento (pontos)','float',1],
['titulo_regex','Padrão de título de seção (regex)','text',1],['parada_regex','Padrão de parada (regex)','text',1]];
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error)}
async function api(url,data){const response=await fetch(url,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Editor-Token':TOKEN},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'Falha na operação');return result}
async function action(fn){document.querySelectorAll('button').forEach(b=>b.disabled=true);try{await fn()}catch(e){status(e.message,true)}finally{document.querySelectorAll('button').forEach(b=>b.disabled=false)}}
function setProfile(p){for(const [key,,type] of fields){const input=$(key);if(type==='bool')input.checked=p[key];else input.value=p[key]===null?'':Array.isArray(p[key])?p[key].join(', '):p[key]}$('model').value=''}
function getProfile(){const p={};for(const [key,label,type]of fields){const input=$(key),v=input.value.trim();if(type==='bool')p[key]=input.checked;else if(type.endsWith('?')&&!v)p[key]=null;else if(type.startsWith('array')){p[key]=v.split(',').map(x=>{if(!x.trim())throw Error(label+': informe as posições');return Number(x.trim())})}else if(type.startsWith('int')||type.startsWith('float')){if(!v)throw Error(label+': preencha o campo');p[key]=Number(v);if(!Number.isFinite(p[key]))throw Error(label+': número inválido')}else p[key]=v}return p}
async function refresh(selected){const data=await api('/api/profiles');$('profileList').replaceChildren();for(const name of data.files)$('profileList').add(new Option(name,name));if(selected)$('profileList').value=selected}
async function openPDF(data){status('Abrindo PDF…');const result=await api('/api/open',data);pdfId=result.id;$('pdfInfo').textContent=result.name+' — '+result.pages+' páginas';$('page').replaceChildren();for(let i=1;i<=result.pages;i++)$('page').add(new Option('Página '+i,i));$('output').replaceChildren();await showPage();status('PDF aberto. Ajuste as regras e clique em Testar perfil.')}
async function showPage(){if(!pdfId)return;const data=await api('/api/page?id='+pdfId+'&page='+$('page').value);activePage=data;$('canvas').innerHTML=data.svg;applyLayers()}
function applyLayers(){document.querySelectorAll('[data-layer]').forEach(input=>document.querySelectorAll('.layer.'+input.dataset.layer).forEach(g=>g.style.display=input.checked?'inline':'none'))}
async function init(){const data=await api('/api/init');defaults=data.defaults;models=data.models;
for(const [key,label,type,advanced] of fields){const wrapper=document.createElement('label');wrapper.textContent=label;let input;if(type==='select'||type==='repeat-select'){input=document.createElement('select');const choices=type==='repeat-select'?[['auto','Automático'],['nao_tratar','Não tratar'],['tratar','Tratar']]:[['auto','Automático'],['1','Uma coluna'],['2','Duas colunas']];for(const [v,l] of choices)input.add(new Option(l,v))}else{input=document.createElement('input');input.type=type==='bool'?'checkbox':type.startsWith('int')||type.startsWith('float')?'number':'text';if(input.type==='number'){input.step=type.startsWith('int')?'1':'any';input.min='0'}}input.id=key;wrapper.append(input);if(type==='repeat-select'){const hint=document.createElement('p');hint.className='hint';hint.textContent='Automático detecta números repetidos e acrescenta .1, .2…; Tratar permite esses reinícios; Não tratar interrompe o teste ao encontrar duplicatas.';wrapper.append(hint)}$(advanced?'advanced':'basic').append(wrapper)}
for(const name of Object.keys(models))$('model').add(new Option(name,name));
for(const [key,label]of [['recortes','Recortes'],['numeros','Números'],['colunas','Alinhamento'],['limites','Limites'],['marcadores','Seções'],['objetos','Objetos']]){const labelEl=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=key!=='objetos';input.dataset.layer=key;input.onchange=applyLayers;labelEl.append(input,' '+label);$('layers').append(labelEl)}
setProfile(defaults);await refresh();}
$('form').onsubmit=e=>e.preventDefault();
$('new').onclick=()=>{setProfile(defaults);$('nome').value='Meu perfil';$('filename').value='meu_perfil.json';status('Novo perfil. Ajuste os campos antes de salvar.')};
$('load').onclick=()=>action(async()=>{const name=$('profileList').value;if(!name)throw Error('Nenhum perfil disponível');setProfile((await api('/api/profile?name='+encodeURIComponent(name))).profile);$('filename').value=name;status('Perfil carregado: '+name+'. Teste para atualizar as marcações.')});
$('model').onchange=()=>{const p=models[$('model').value];if(p)for(const key of Object.keys(p))$(key).value=p[key]??''};
$('save').onclick=()=>action(async()=>{const data={name:$('filename').value,profile:getProfile()};let result=await api('/api/save',data);if(result.exists){if(!confirm('Substituir o perfil '+result.name+'?'))return;result=await api('/api/save',{...data,overwrite:true})}await refresh(result.name);status('Perfil salvo em '+result.path)});
$('download').onclick=()=>action(async()=>{const result=await api('/api/validate',{profile:getProfile()});const url=URL.createObjectURL(new Blob([JSON.stringify(result.profile,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=$('filename').value||'perfil.json';a.click();URL.revokeObjectURL(url);status('JSON validado e enviado para download.')});
$('upload').onchange=()=>action(async()=>{const file=$('upload').files[0];if(!file)return;const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));await openPDF({name:file.name,content:btoa(binary)})});
$('openPath').onclick=()=>action(()=>openPDF({path:$('pdfPath').value}));
$('page').onchange=()=>action(showPage);
$('test').onclick=()=>action(async()=>{if(!pdfId)throw Error('Abra um PDF primeiro');status('Testando o perfil em todas as páginas…');const result=await api('/api/test',{id:pdfId,profile:getProfile()});await showPage();status(result.count+' questões detectadas.\n'+result.warnings.join('\n')+'\nMarcações correspondem ao último teste. Teste novamente após editar os campos.',!!result.error);if(result.error)status(result.error+'\n'+$('status').textContent,true)});
$('extract').onclick=()=>action(async()=>{if(!pdfId)throw Error('Abra um PDF primeiro');status('Gerando as imagens e o relatório de revisão…');const result=await api('/api/extract',{id:pdfId,profile:getProfile()});status('Imagens e revisão salvas em '+result.path);$('output').replaceChildren();const link=document.createElement('a');link.href=result.url;link.target='_blank';link.rel='noopener';link.textContent='Abrir relatório de revisão';$('output').append(link)});
$('canvas').onclick=e=>{const svg=$('canvas').querySelector('svg');if(!svg)return;const pick=$('pick').value;if(!pick){const g=e.target.closest('g[data-info]');if(g)$('info').textContent=g.dataset.info;return}const point=svg.createSVGPoint();point.x=e.clientX;point.y=e.clientY;const pos=point.matrixTransform(svg.getScreenCTM().inverse());if(pos.x<0||pos.y<0||pos.x>activePage.width||pos.y>activePage.height)return;
if(pick.startsWith('coluna')){let xs=$('inicios_colunas').value.trim()?$('inicios_colunas').value.split(',').map(Number):[];const x=Number((pos.x/activePage.width).toFixed(4));if(pick==='coluna1'){xs[0]=x}else{if(!xs.length){status('Marque primeiro o início da coluna 1.',true);return}xs[1]=x;$('colunas').value='2'}$('inicios_colunas').value=xs.join(', ')}else $(pick).value=(pos.y/activePage.height).toFixed(4);status('Posição preenchida. Clique em Testar perfil para atualizar a prévia.')};
init().catch(e=>status(e.message,true));
</script></body></html>'''


class EditorServer(HTTPServer):
    def __init__(self, address, temporary):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.temporary = Path(temporary)
        self.documents = {}
        self.outputs = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, data, status=200, mime='application/json; charset=utf-8'):
        payload = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self):
        port = self.server.server_port
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def do_GET(self):
        if not self.allowed():
            return self.respond({'error': 'Host inválido.'}, 403)
        route = urlparse(self.path)
        query = parse_qs(route.query)
        try:
            if route.path == '/':
                return self.respond(PAGE.replace('__TOKEN__', json.dumps(self.server.token)).encode(), mime='text/html; charset=utf-8')
            if route.path == '/api/init':
                return self.respond({'defaults': DEFAULT_PROFILE, 'models': MODELS})
            if route.path == '/api/profiles':
                return self.respond({'files': sorted(p.name for p in (V3 / 'perfis').glob('*.json'))})
            if route.path == '/api/profile':
                return self.respond({'profile': load_profile(self.profile_path(query['name'][0]))})
            if route.path == '/api/page':
                return self.preview(query['id'][0], int(query['page'][0]))
            if route.path == '/api/image':
                return self.page_image(query['id'][0], int(query['page'][0]))
            if route.path.startswith('/output/'):
                return self.output_file(route.path)
            return self.respond({'error': 'Página não encontrada.'}, 404)
        except Exception as error:
            self.respond({'error': str(error)}, 400)

    def profile_path(self, name):
        name = name.strip()
        if not re.fullmatch(r'[\w-]+(?:\.json)?', name, flags=re.UNICODE):
            raise ValueError('Use letras, números, _ e - no nome do arquivo.')
        if not name.endswith('.json'):
            name += '.json'
        return V3 / 'perfis' / name

    def document(self, ident):
        if ident not in self.server.documents:
            raise ValueError('PDF não disponível. Abra o arquivo novamente.')
        return self.server.documents[ident]

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-Editor-Token') != self.server.token:
            return self.respond({'error': 'Requisição não autorizada.'}, 403)
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.respond({'error': 'Origem inválida.'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 100 * 1024 * 1024:
                raise ValueError('Requisição vazia ou maior que 100 MB. Para PDFs grandes, use o caminho completo.')
            data = json.loads(self.rfile.read(size))
            route = urlparse(self.path).path
            if route == '/api/open':
                return self.open_pdf(data)
            profile = load_profile(data['profile'])
            if route == '/api/validate':
                return self.respond({'profile': profile})
            if route == '/api/save':
                path = self.profile_path(data['name'])
                if path.exists() and not data.get('overwrite'):
                    return self.respond({'exists': True, 'name': path.name})
                path.parent.mkdir(parents=True, exist_ok=True)
                # Arquivo temporário na mesma pasta para substituição atômica.
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as stream:
                    temp = Path(stream.name)
                    json.dump(profile, stream, ensure_ascii=False, indent=2)
                try:
                    temp.replace(path)
                finally:
                    temp.unlink(missing_ok=True)
                return self.respond({'name': path.name, 'path': str(path)})
            doc = self.document(data['id'])
            if route == '/api/test':
                from extrator_v3 import detect
                diagnostics = {}
                error = None
                try:
                    questions, warnings = detect(doc['path'], profile=profile, diagnostics=diagnostics)
                except ValueError as exc:
                    questions, warnings, error = [], [], str(exc)
                doc['diagnostics'] = diagnostics
                return self.respond({'count': len(questions), 'warnings': warnings, 'error': error})
            if route == '/api/extract':
                from extrator_v3 import run
                output = run(doc['path'], profile=profile, destination=V3 / 'saidas')
                ident = secrets.token_hex(12)
                self.server.outputs[ident] = output.resolve()
                return self.respond({'path': str(output), 'url': f'/output/{ident}/revisao/index.html'})
            return self.respond({'error': 'Operação não encontrada.'}, 404)
        except Exception as error:
            self.respond({'error': str(error)}, 400)

    def open_pdf(self, data):
        import base64
        import pypdfium2 as pdfium
        ident = secrets.token_hex(12)
        if 'path' in data:
            path = Path(data['path'].strip().strip('"')).expanduser().resolve()
        else:
            name = Path(data.get('name', 'prova.pdf')).name
            if not name.lower().endswith('.pdf'):
                raise ValueError('Escolha um arquivo PDF.')
            folder = self.server.temporary / ident
            folder.mkdir()
            path = folder / name
            path.write_bytes(base64.b64decode(data['content'], validate=True))
        if path.suffix.lower() != '.pdf' or not path.is_file():
            raise ValueError('O caminho deve apontar para um PDF existente.')
        with pdfium.PdfDocument(str(path)) as pdf:
            count = len(pdf)
        if not count:
            raise ValueError('PDF sem páginas.')
        self.server.documents[ident] = {'path': path, 'diagnostics': {}}
        return self.respond({'id': ident, 'name': path.name, 'pages': count})

    def preview(self, ident, number):
        import pypdfium2 as pdfium
        from revisao_v3 import svg_layers
        doc = self.document(ident)
        with pdfium.PdfDocument(str(doc['path'])) as pdf:
            if not 1 <= number <= len(pdf):
                raise ValueError('Página inválida.')
            with closing(pdf[number - 1]) as page:
                width, height = page.get_size()
        diagnostics = doc['diagnostics'].get('paginas', [])
        layers = svg_layers(diagnostics[number - 1]) if diagnostics else ''
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Página {number}">'
               f'<image href="/api/image?id={ident}&amp;page={number}" width="{width}" height="{height}"/>{layers}</svg>')
        self.respond({'svg': svg, 'width': width, 'height': height})

    def page_image(self, ident, number):
        import pypdfium2 as pdfium
        from recorte import render
        doc = self.document(ident)
        with pdfium.PdfDocument(str(doc['path'])) as pdf:
            if not 1 <= number <= len(pdf):
                raise ValueError('Página inválida.')
            with closing(pdf[number - 1]) as page:
                with closing(render(page, 1200 / page.get_width())) as image:
                    stream = io.BytesIO()
                    image.save(stream, format='PNG')
        self.respond(stream.getvalue(), mime='image/png')

    def output_file(self, route):
        import mimetypes
        parts = route.split('/', 3)
        root = self.server.outputs.get(parts[2])
        if root is None or len(parts) != 4:
            raise ValueError('Resultado não disponível.')
        path = (root / parts[3]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Arquivo não disponível.')
        self.respond(path.read_bytes(), mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--porta', type=int, default=8765, help='Porta local; padrão: 8765')
    parser.add_argument('--sem-navegador', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.porta <= 65535:
        parser.error('A porta deve estar entre 0 e 65535.')
    try:
        import pdfplumber
        import pypdfium2
        import PIL
    except ImportError:
        parser.exit(1, 'Instale as dependências da V3:\npython -m pip install -r versao3/requirements.txt\n')
    try:
        with tempfile.TemporaryDirectory(prefix='editor_perfis_') as temporary:
            with EditorServer(('127.0.0.1', args.porta), temporary) as server:
                url = f'http://127.0.0.1:{server.server_port}'
                print(f'Editor de perfis: {url}\nMantenha este terminal aberto. Ctrl+C para encerrar.')
                if not args.sem_navegador:
                    webbrowser.open(url)
                server.serve_forever()
    except KeyboardInterrupt:
        print('\nEditor encerrado.')
    except OSError as error:
        parser.exit(1, f'Não foi possível iniciar: {error}\nTente outra porta: python gerador_perfis.py --porta 8766\n')


if __name__ == '__main__':
    main()
