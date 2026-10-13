# PDF + coordenadas → imagens locais

1. Envie o PDF para a IA com o texto de `prompt_ia.txt`.
2. Coloque `prova1.pdf` na pasta do script e execute `python extrator.py`.
3. Se existir `prova1.json`, o programa usa esse arquivo automaticamente. Caso contrário, ele espera você colar a resposta da IA no console.
4. Após colar o JSON (pode ter várias linhas), pressione Enter, digite `FIM` em uma linha separada e pressione Enter novamente. O programa cria `prova1/questao_1.png`, `prova1/questao_2.png`, etc., sem salvar o JSON colado. Digite `PULAR` para ignorar um PDF.

Questões com várias partes são unidas verticalmente, na ordem do JSON, em uma única imagem. O programa processa todos os PDFs da pasta, como `prova1`, `prova2` e `prova3`, pedindo coordenadas para cada arquivo sem JSON. Não chama IA nem envia arquivos. Execute em um PowerShell ou terminal aberto para ver os pedidos de entrada.

## Instalação

No PowerShell, dentro da pasta do programa:

```powershell
python -m pip install -r requirements.txt
```

## Executar

```powershell
python extrator.py
```

Para uma prova específica, outra pasta ou maior resolução:

```powershell
python extrator.py "prova1.pdf"
python extrator.py "C:\Provas" --dpi 300
```

Sem argumentos, procura na pasta onde está `extrator.py`. A saída fica sempre ao lado do PDF, numa pasta com o mesmo nome, sem `.pdf`. O padrão é 200 DPI. Se `prova1` já existir, cria `prova1 (1)`, depois `prova1 (2)` e assim por diante, preservando os resultados anteriores. Mesmo pastas vazias ou arquivos com esses nomes são preservados.

## JSON aceito

```json
[
  {
    "questao": "1",
    "partes": [
      {"pagina": 1, "coordenadas": {"x0": 50, "y0": 100, "x1": 400, "y1": 500}}
    ]
  },
  {
    "questao": "2",
    "partes": [
      {"pagina": 1, "coordenadas": {"x0": 50, "y0": 510, "x1": 400, "y1": 800}},
      {"pagina": 2, "coordenadas": {"x0": 50, "y0": 50, "x1": 400, "y1": 200}}
    ]
  }
]
```

Os números acima são exemplos. Salve a lista como JSON puro, sem aspas ao redor da lista nem cercas de Markdown. A página começa em 1 e corresponde à ordem no arquivo, não à numeração impressa. IDs devem ser únicos.

## Unidade das coordenadas

O padrão agora é **grade normalizada de 0 a 1000**, relativa à página inteira na orientação em que ela é exibida. Origem no canto superior esquerdo: X cresce para a direita, Y para baixo. `x0,y0` é o canto superior esquerdo e `x1,y1` é o inferior direito. Assim, `[0,0,500,1000]` representa a metade esquerda de qualquer página. O Python converte a grade para a resolução final localmente. A IA não precisa descobrir o tamanho do PDF ou o DPI.

**Migração:** JSONs feitos com o prompt antigo usam pontos do PDF. Para esses arquivos, execute `python extrator.py --unidade pontos`. Não misture unidades em um mesmo lote; o programa não consegue deduzi-las somente pelos números.

## Melhorar a marcação pela IA

Use o novo `prompt_ia.txt`. Como primeira tentativa, envie lotes pequenos, de 1 a 3 páginas, mantendo juntas as páginas com continuidade. Se o chat tiver dificuldade para ver o layout do PDF, envie imagens completas dessas páginas sem recortar margens. Preserve os números de página ao juntar as respostas.

A grade elimina ambiguidades de escala, mas não garante que a IA localize corretamente cada limite. Confira os recortes. Se persistirem erros, uma alternativa é usar a IA para identificar o começo/fim pelo texto e localizar esses trechos com extração de texto ou OCR local; esse método ainda não está implementado.

Se a IA devolver **pixels**, é necessário conhecer o DPI da imagem usada para marcar as regiões. Por exemplo, para coordenadas de uma renderização a 150 DPI:

```powershell
python extrator.py --unidade pixels --dpi-referencia 150
```

O DPI de referência descreve a imagem usada pela IA; `--dpi` controla apenas a imagem final. Não é possível deduzir a escala de coordenadas em pixels somente pelos quatro números. Se o chat redimensionar a imagem para dimensões desconhecidas, peça coordenadas em pontos ou normalizadas.

Também aceita os mesmos campos `x0,y0,x1,y1` com valores de 0 a 1 usando `--unidade normalizada`.

Todas as regiões de uma prova são validadas antes de gerar imagens. JSON colado com sintaxe inválida pode ser colado novamente. Um erro nos limites ou no processamento de uma prova não impede processar as outras. O programa renderiza uma página por vez e usa arquivos temporários locais para unir partes; DPI alto aumenta o consumo de memória. A precisão dos limites depende da IA, e ampliar um escaneamento não recupera detalhes ausentes no original.
