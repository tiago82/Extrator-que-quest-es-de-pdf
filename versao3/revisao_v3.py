"""Relatório visual local das evidências usadas pelo detector V3."""
from contextlib import closing
from html import escape
import json

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

from recorte import render

COLORS = {'início': '#2563eb', 'continuação': '#d97706', 'apoio': '#9333ea',
          'aceito': '#15803d', 'rejeitado': '#dc2626', 'coluna': '#0891b2'}


def rectangle(box, color, title, fill='none', opacity=1):
    x0,y0,x1,y1 = box
    return (f'<g data-info="{escape(title, quote=True)}"><title>{escape(title)}</title>'
            f'<rect x="{x0}" y="{y0}" width="{max(0,x1-x0)}" height="{max(0,y1-y0)}" '
            f'fill="{fill}" fill-opacity="{opacity}" stroke="{color}" stroke-width="1.2"/></g>')


def svg_layers(page):
    width,height = page['largura'],page['altura']
    groups = {k: [] for k in ['limites','colunas','numeros','marcadores','recortes','objetos']}
    limits = page['limites']
    if limits:
        for box, info in [([0,0,width,limits['topo']], 'Cabeçalho excluído: ' + limits['origem_topo']),
                          ([0,limits['base'],width,height], 'Rodapé excluído: ' + limits['origem_base'])]:
            groups['limites'].append(rectangle(box,'#64748b',info,'#64748b',.2))
    for column in page['colunas']:
        x,t = column['inicio'],column['tolerancia']
        info = f"Coluna {column['coluna']}; X={x:.2f}; tolerância +/- {t:g} pontos; origem: {column['origem']}"
        groups['colunas'].append(rectangle([x-t,limits['topo'],x+t,limits['base']],COLORS['coluna'],info,COLORS['coluna'],.07))
        groups['colunas'].append(f'<path d="M{x} {limits["topo"]} V{limits["base"]}" stroke="{COLORS["coluna"]}" stroke-width=".6" stroke-dasharray="3 3"/>')
    for candidate in page['candidatos']:
        color = COLORS['aceito' if candidate['aceito'] else 'rejeitado']
        info = f"Número {candidate['texto']}: {'ACEITO' if candidate['aceito'] else 'REJEITADO'}\n{candidate['motivo']}\nFonte: {candidate['fonte']}"
        groups['numeros'].append(rectangle(candidate['bbox'],color,info,color,.1))
    for marker in page['marcadores']:
        info = f"{'Parada' if marker['tipo']=='stop' else 'Nova seção'}: {marker['texto']}\nDivide o fluxo em Y={marker['y_divisao']:.2f}."
        groups['marcadores'].append(rectangle(marker['bbox'],'#be185d',info,'#be185d',.1))
    for region in page['regioes']:
        color = COLORS[region['tipo']]
        ident = region['questao'] or 'sem destino'
        info = f"Q{ident}: {region['tipo']}\nColuna {region['coluna']}; {region['caracteres']} caracteres; {len(region['graficos'])} objetos gráficos.\nMargem: {region['margem_pontos']} pontos.\nCaixa: " + ', '.join(f'{v:.2f}' for v in region['bbox'])
        groups['recortes'].append(rectangle(region['bbox'],color,info))
        x,y = region['bbox'][:2]
        groups['recortes'].append(f'<text x="{x+2}" y="{max(8,y-2)}" fill="{color}" font-size="7" font-family="Arial">Q{escape(str(ident))} · {region["tipo"]}</text>')
        groups['objetos'].append(rectangle(region['bbox_conteudo'],'#a855f7','Extensão do conteúdo antes da margem'))
        for graphic in region['graficos']:
            groups['objetos'].append(rectangle(graphic['bbox'],'#c084fc',f"Objeto {graphic['tipo']} usado para calcular a extensão."))
    return ''.join(f'<g class="layer {key}">{"".join(items)}</g>' for key,items in groups.items())


def annotated_png(im, page, name, profile_name):
    im = im.convert('RGBA')
    overlay = Image.new('RGBA', im.size)
    draw = ImageDraw.Draw(overlay)
    sx,sy = im.width/page['largura'],im.height/page['altura']
    def box(b):
        return [b[0]*sx,b[1]*sy,b[2]*sx,b[3]*sy]
    limits = page['limites']
    if limits:
        draw.rectangle(box([0,0,page['largura'],limits['topo']]),fill=(100,116,139,50))
        draw.rectangle(box([0,limits['base'],page['largura'],page['altura']]),fill=(100,116,139,50))
    for column in page['colunas']:
        x,t = column['inicio'],column['tolerancia']
        draw.rectangle(box([x-t,limits['topo'],x+t,limits['base']]),fill=(8,145,178,20))
        draw.line(box([x,limits['topo'],x,limits['base']]),fill=COLORS['coluna'],width=2)
    for region in page['regioes']:
        draw.rectangle(box(region['bbox']),outline=COLORS[region['tipo']],width=3)
    for marker in page['marcadores']:
        draw.rectangle(box(marker['bbox']),outline='#be185d',width=3)
    for candidate in page['candidatos']:
        draw.rectangle(box(candidate['bbox']),outline=COLORS['aceito' if candidate['aceito'] else 'rejeitado'],width=3)
    combined = Image.alpha_composite(im,overlay).convert('RGB')
    canvas = Image.new('RGB',(combined.width,combined.height+145),'white')
    canvas.paste(combined,(0,80))
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
    except OSError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(canvas)
    draw.text((15,10),f"Página {page['pagina']} | Perfil: {profile_name}",font=font,fill='#0f172a')
    legend = [('Início','#2563eb'),('Continuação','#d97706'),('Apoio','#9333ea'),
              ('Número aceito','#15803d'),('Rejeitado','#dc2626'),('Colunas','#0891b2'),('Seção/parada','#be185d')]
    x=15
    for label,color in legend:
        draw.text((x,45),label,font=font,fill=color)
        x += draw.textlength(label,font=font)+25
    message = f"{len(page['regioes'])} regiões | Abra index.html para ligar camadas e consultar motivos."
    if not page['processada']:
        message = 'Página ignorada: anterior ao início detectado/configurado.'
    draw.text((15,combined.height+100),message,font=font,fill='#334155')
    canvas.save(name)
    canvas.close()
    combined.close()
    overlay.close()
    im.close()


def generate_review(pdf, output, diagnostics):
    review = output / 'revisao'
    originals = review / 'originais'
    originals.mkdir(parents=True)
    (output/'diagnostico_v3.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')
    sections=[]
    with pdfium.PdfDocument(str(pdf)) as doc:
        for page_info in diagnostics['paginas']:
            number=page_info['pagina']
            with closing(doc[number-1]) as page:
                im=render(page,1400/page.get_width())
                im.save(originals/f'pagina_{number:02d}.png')
                annotated_png(im,page_info,review/f'pagina_{number:02d}.png',diagnostics['perfil']['nome'])
                im.close()
            summaries = [f"Q{r['questao'] or '?'} — {r['tipo']}, coluna {r['coluna']}: {r['caracteres']} caracteres e {len(r['graficos'])} objetos gráficos." for r in page_info['regioes']]
            if not page_info['processada']:
                summaries=['Página anterior ao início detectado/configurado; sem recortes.']
            width,height=page_info['largura'],page_info['altura']
            sections.append(f'<section class="page" id="page-{number}"><h2>Página {number}</h2>'
                f'<p>{escape(" | ".join(summaries))}</p><svg viewBox="0 0 {width} {height}" role="img" aria-label="Revisão da página {number}">'
                f'<image href="originais/pagina_{number:02d}.png" width="{width}" height="{height}"/>{svg_layers(page_info)}</svg></section>')
    options=''.join(f'<option value="{p["pagina"]}">Página {p["pagina"]}</option>' for p in diagnostics['paginas'])
    toggles=''.join(f'<label><input type="checkbox" data-layer="{key}" {"" if key=="objetos" else "checked"}>{label}</label>'
        for key,label in [('recortes','Recortes: azul início, laranja continuação, roxo apoio'),('numeros','Números: verde aceito, vermelho rejeitado'),
                          ('colunas','Colunas e faixa de tolerância: ciano'),('limites','Cabeçalho/rodapé excluídos: cinza'),
                          ('marcadores','Títulos e paradas: rosa'),('objetos','Extensão do conteúdo e objetos gráficos')])
    html='''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisão V3</title><style>
body{margin:0;background:#eef2f6;color:#172033;font:15px system-ui}header{padding:18px 26px;background:#fff;border-bottom:1px solid #cbd5e1}
main{display:grid;grid-template-columns:320px minmax(0,1fr);gap:20px;padding:20px}aside{position:sticky;top:15px;align-self:start;background:white;padding:18px;border-radius:10px}
label{display:block;margin:14px 0;line-height:1.5}select{padding:8px;width:100%}section{background:white;padding:20px;border-radius:10px;margin-bottom:20px}
svg{display:block;width:100%;max-width:1000px;margin:auto}g[data-info]{cursor:pointer}g[data-info]:hover rect{stroke-width:2.5}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px system-ui;padding:12px;background:#f1f5f9}p{line-height:1.5}
.objetos{display:none}@media(max-width:850px){main{grid-template-columns:1fr}aside{position:static}}
</style><header><h1>Como os cortes foram calculados</h1><p>''' + escape(pdf.name) + ' | Perfil: '+escape(diagnostics['perfil']['nome'])+'''</p></header>
<main><aside><strong>Camadas de diagnóstico</strong>''' + toggles + '<hr><label>Página<select id="selector"><option value="all">Todas</option>'+options+'''</select></label>
<p>Clique em uma marcação para ver o motivo, a fonte ou as medidas. Passe o mouse para uma descrição breve.</p><pre id="details">Selecione uma marcação na página.</pre>
<details><summary>Perfil utilizado</summary><pre>''' + escape(json.dumps(diagnostics['perfil'],ensure_ascii=False,indent=2))+'''</pre></details>
<details><summary>Avisos</summary><p>''' + escape(' | '.join(diagnostics['avisos']))+'''</p></details>
<p>Estas marcas explicam regras geométricas; não representam confiança estatística nem validação semântica.</p></aside><div>'''+''.join(sections)+'''</div></main>
<script>
document.querySelectorAll('[data-layer]').forEach(input=>input.addEventListener('change',()=>document.querySelectorAll('.'+input.dataset.layer).forEach(layer=>layer.style.display=input.checked?'inline':'none')));
document.addEventListener('click',event=>{const g=event.target.closest('g[data-info]');if(g)document.getElementById('details').textContent=g.dataset.info});
document.getElementById('selector').addEventListener('change',function(){document.querySelectorAll('.page').forEach(p=>p.hidden=this.value!=='all'&&p.id!=='page-'+this.value)});
</script></html>'''
    (review/'index.html').write_text(html,encoding='utf-8')
