# Extrator V3: teste de detecção automática local

Esta versão usa o texto e suas posições no PDF. Não usa IA, não pede JSON e não envia arquivos à internet. A V1 está preservada em `../versao1/`. O recortador independente da V3 fica em `recorte.py`.

## Executar

```powershell
python -m pip install -r requirements.txt
python extrator_v3.py
```

Procura PDFs em `entradas/`, dentro da pasta da V3, e grava resultados em `saidas/`. Para um PDF específico:

```powershell
python extrator_v3.py "prova1.pdf"
```

Gera `prova1_v3`, `prova1_v3 (1)` etc. Dentro ficam as PNGs das questões, a pasta `revisao` com limites desenhados nas páginas, um JSON de coordenadas gerado localmente e `avisos.txt`. Não é necessário fornecer ou editar o JSON.

## Revisão explicada

Abra `revisao/index.html` no navegador. É um relatório local, sem servidor ou conexão à internet. Selecione uma página e ligue/desligue as camadas. Passe o mouse ou clique em uma marcação para ver os motivos e medidas. A pasta também contém as PNGs anotadas, para revisão sem navegador.

| Marca | Evidência mostrada |
|---|---|
| Azul | Recorte iniciado por um número de questão. |
| Laranja | Trecho associado como continuação de uma questão anterior. |
| Roxo | Material de apoio associado à primeira questão da seção. |
| Verde | Número aceito por padrão, fonte, área útil e alinhamento. |
| Vermelho | Token numérico rejeitado ou numa página ignorada; o painel explica o motivo. |
| Ciano | Alinhamento esperado do número e faixa de tolerância da coluna. |
| Cinza | Cabeçalho e rodapé excluídos; informa se o limite veio do perfil, de linha horizontal ou de aproximação. |
| Rosa | Título de seção ou marcador de parada, como RASCUNHO. |

A camada opcional de objetos mostra a extensão do conteúdo antes da margem e os objetos gráficos usados no cálculo. Nos recortes, o painel informa a coluna, a contagem de caracteres/objetos e a margem aplicada. `diagnostico_v3.json` registra esses dados para inspeção técnica. Tokens que nem correspondem ao padrão de numeração não são destacados; não é um rastreamento de cada palavra do PDF.

Para ajustar o perfil: números corretos vermelhos sugerem conferir fonte, padrão ou alinhamento; uma faixa ciano deslocada sugere configurar `inicios_colunas`; conteúdo sob cinza sugere ajustar os limites úteis; uma continuação laranja errada sugere conferir marcadores de seção/parada ou o layout. As cores indicam decisões do algoritmo, não garantia de acerto.

Para escolher onde gravar ou forçar uma ou duas colunas:

```powershell
python extrator_v3.py "C:\Provas\prova.pdf" --saida "." --colunas 2 --dpi 200
```

## Como funciona e limites

No perfil padrão, procura números de dois ou três dígitos seguidos de ponto, em negrito, alinhados ao início das colunas, com numeração começando em 01. As regras podem ser modificadas por perfil. Segue coluna esquerda, direita, próxima página. Usa posições de caracteres e objetos gráficos para reduzir espaços vazios. Trata títulos `PROVA ...` e `RASCUNHO` como divisões e pode incluir uma tabela de apoio antes da primeira questão da seção.

É uma heurística experimental para provas com layout semelhante ao exemplo UECE. Não inclui OCR para PDFs escaneados; não trata automaticamente numeração reiniciada, colunas irregulares ou identificação semântica de todo texto compartilhado. A tabela geral de uma seção é anexada à primeira questão, não a todas: confira se outras questões precisam dela. Revise as imagens e a pasta `revisao` antes de usar em outro PDF.

No PDF v20261fisquig1.pdf foram detectadas 40 questões e continuações de coluna nas questões 04, 11, 20, 25 e 33. Os resultados foram inspecionados visualmente. A tabela de Química foi incluída junto à questão 21.

## Perfis: adaptar a outra prova sem editar o Python

Um perfil é um pequeno JSON com regras reutilizáveis de layout, não uma lista de cortes. Crie uma vez por família de provas e reutilize.

```powershell
python extrator_v3.py "prova.pdf" --perfil "perfis/uece.json"
python extrator_v3.py "outra_prova.pdf" --perfil "perfis/uma_coluna.json"
```

O perfil UECE inclui a conferência de 40 questões. O padrão sem `--perfil` usa as regras de layout UECE, mas não exige essa quantidade. O perfil de uma coluna é um ponto de partida; não foi validado em uma segunda prova real.

Copie `perfis/uma_coluna.json` para `perfis/minha_banca.json` e ajuste o necessário. Campos omitidos usam os padrões definidos em `perfis_v3.py`. Campos desconhecidos, tipos incorretos e expressões inválidas são rejeitados, evitando erros silenciosos de configuração.

| Campo | Significado |
|---|---|
| `nome` | Nome descritivo do perfil. |
| `numero_regex` | Padrão do token que marca o número. Precisa capturar os dígitos no grupo `(?P<numero>...)`. |
| `prefixo_numero_regex` | null para número isolado; ou padrão da palavra anterior, como `QUEST[ÃA]O`. Associa palavra e número próximos na mesma linha. |
| `exigir_negrito` | Se true, exige que o nome da fonte contenha `bold`. |
| `primeira_questao` | Número que inicia o processamento; útil para cadernos que começam em 91, por exemplo. |
| `ignorar_paginas_iniciais` | Quantidade de páginas iniciais a ignorar, como capa e instruções. |
| `colunas` | Texto `"auto"`, `"1"` ou `"2"`. `--colunas` substitui esse campo. |
| `detectar_pagina_uma_coluna` | Se true, adapta uma página de duas colunas para largura inteira quando só há rótulos à esquerda e linhas largas imediatamente abaixo desses rótulos. Útil no Poliedro; não é um detector geral de layouts mistos. |
| `inicios_colunas` | null para detectar; ou posições X dos números como frações da largura: `[0.06, 0.54]`, por exemplo. Não são os limites de corte. |
| `limite_superior` | null para detectar linha de cabeçalho; ou fração da altura, como 0.07. |
| `limite_inferior` | null para detectar linha de rodapé; ou fração da altura, como 0.93. |
| `margem_pontos` | Folga ao redor do conteúdo; padrão 3 pontos. Continua limitada ao bloco detectado. |
| `recuo_inicio_pontos` | Quanto subir acima da caixa do rótulo de questão; padrão 0,2 ponto. No Poliedro, 3 pontos preservam acentos que ultrapassam a caixa tipográfica. |
| `tolerancia_alinhamento` | Distância máxima, em pontos, entre o número e o início estimado da coluna; padrão 8. |
| `titulo_regex` | Padrão que reconhece o título de uma nova seção. |
| `parada_regex` | Padrão de área a excluir, como RASCUNHO. |
| `quantidade_esperada` | null ou total esperado. Divergência gera aviso; não prova que os recortes estão corretos. |

Exemplos de `numero_regex`, com a duplicação de barras exigida pelo JSON:

```json
{"numero_regex": "(?P<numero>\\d{1,3})[.)]"}
```

Aceita `1.`, `1)`, `01.` e `100)`. Para um token como `Q01`:

```json
{"numero_regex": "Q(?P<numero>\\d{1,3})"}
```

O detector aceita um token completo ou uma palavra de prefixo seguida de um número, como `QUESTÃO 91`, usando `prefixo_numero_regex`. O prefixo deve estar até 15 pontos à esquerda do número, com diferença de topo de até 3 pontos; rótulos mais complexos ainda exigem extensão. Títulos e paradas recebem texto em maiúsculas, sem espaços, antes de aplicar o padrão.

O perfil `perfis/poliedro_enem.json` foi testado no 4º simulado Poliedro 2025, Dia 2: numeração de 91 a 180, duas colunas e 90 questões. Ignore a capa e execute:

```powershell
python extrator_v3.py "entradas/prova_poliedro.pdf" --perfil "perfis/poliedro_enem.json"
```

O perfil `perfis/somos_enem.json` foi testado no 5º simulado SOMOS 2025, Dia 2: 90 questões, 91 a 180, com alinhamentos inferidos e adaptação para largura inteira nas páginas 3, 6, 12, 14, 17, 27 e 32. A página final de divulgação não foi incluída nos recortes.

```powershell
python extrator_v3.py "entradas/prova_somos.pdf" --perfil "perfis/somos_enem.json"
```

Cada resultado inclui `perfil_usado.json`, com as regras efetivamente usadas naquela execução. Para corrigir pontualmente, edite `coordenadas_v3.json`, salve uma cópia com o nome do PDF e use a V1 com `--unidade pontos`. A V3 não lê essas correções automaticamente.

## O que acontece dentro do programa

1. `pdfplumber` lê caracteres, fontes, posições, imagens e objetos vetoriais do arquivo. Essa etapa não resolve as questões e não exige um modelo de linguagem.
2. `number_words` aplica o padrão do perfil para encontrar candidatos a números de questão. Alinhamento e fonte ajudam a distingui-los de números de listas internas.
3. `column_starts` agrupa posições X semelhantes. A partir da primeira questão, `detect` identifica até duas colunas regulares. O perfil pode informar posições fixas se a inferência falhar.
4. `page_limits` exclui cabeçalhos e rodapés por linhas horizontais longas, ou pelos limites configurados. Sem linhas reconhecidas, usa limites aproximados: 6,5% a 92,5% da altura. Essas porcentagens podem excluir conteúdo em outro layout.
5. `detect` percorre os blocos na ordem de leitura. Ao encontrar um novo número, encerra a questão anterior. Ao mudar de coluna sem novo número, considera o texto inicial como continuação da questão ativa.
6. `content_box` calcula a caixa dos caracteres e objetos gráficos daquele trecho e acrescenta margem. Ela não interpreta a função semântica de uma figura: um objeto fora da região, atravessando colunas ou mal associado pode exigir ajuste.
7. O módulo `recorte.py` gera os pixels do PDF original no DPI escolhido, recorta cada parte e monta a PNG final. Na V3, as coordenadas intermediárias são em pontos do PDF, não na grade 0–1000 da IA.
8. A revisão desenha retângulos sobre as páginas; avisos registram saltos de numeração e divergências de quantidade. Esses checks detectam alguns problemas, mas não verificam todo o conteúdo.

## Como saber se outra prova funciona

Teste uma prova da nova família, confira todas as PNGs e as páginas de revisão e ajuste um perfil. Se ela tiver texto extraível, números reconhecíveis, uma ou duas colunas regulares e layout constante, é uma boa candidata. A aprovação de um arquivo não garante os próximos: acompanhe quantidade, sequência e revisão visual.

Capas e instruções numeradas podem ser confundidas com questões: configure `ignorar_paginas_iniciais`. Listas internas alinhadas como questões, fontes com nomes incomuns, questões sem número, numeração reiniciada e layouts que alternam entre uma e duas colunas não estão resolvidos automaticamente.

## Extensão por código

`perfis_v3.py` separa configuração e validação; `extrator_v3.py` contém reconhecimento e segmentação; `recorte.py` mantém o recorte e a montagem. Um novo reconhecedor pode produzir o mesmo contrato interno: uma lista com `questao`, `partes`, `pagina` e `coordenadas` em pontos.

Assim, um futuro módulo OCR ou um detector de rótulos compostos pode substituir a etapa de reconhecimento sem reescrever o renderizador. Essas extensões ainda não estão implementadas. Para textos compartilhados semanticamente ambíguos, a revisão humana ou IA pode continuar sendo necessária.
