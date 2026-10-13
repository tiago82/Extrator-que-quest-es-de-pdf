# Extrator V3

Detecção local por posições do texto, perfis configuráveis e revisão visual com camadas. Esta pasta não depende do código da V1 ou V2. Nenhuma saída antiga ou PDF de teste foi incluído.

## Usar

Abra o PowerShell nesta pasta e instale:

```powershell
python -m pip install -r requirements.txt
```

Coloque os PDFs a processar em `entradas/` e execute:

```powershell
python extrator_v3.py
```

Sem argumentos, lê somente `entradas/`. Grava os resultados em `saidas/nome_v3`, `saidas/nome_v3 (1)` etc. Não sobrescreve resultados anteriores. Se não houver PDF, informa que nenhum foi encontrado.

Para escolher um PDF e um perfil:

```powershell
python extrator_v3.py "entradas/prova.pdf" --perfil "perfis/uece.json"
```

Também pode ler um arquivo externo sem copiá-lo para entradas:

```powershell
python extrator_v3.py "C:\Provas\prova.pdf" --perfil "perfis/uece.json"
```

A saída padrão continua em `saidas/`, mesmo quando o PDF está em outra pasta. Use `--saida "C:\Resultados"` para escolher outro destino e `--dpi 300` para alterar a resolução.

## Organização

- `extrator_v3.py`: detecção e comando principal.
- `recorte.py`: renderização, recorte e montagem local.
- `perfis_v3.py` e `perfis/`: configuração e validação de regras.
- `revisao_v3.py`: páginas anotadas e painel HTML local.
- `entradas/`: seus PDFs, inicialmente vazia.
- `saidas/`: resultados futuros, inicialmente vazia.
- `test_recorte.py` e `test_extrator_v3.py`: verificações automatizadas.
- `GUIA.md`: detalhes do algoritmo, perfis e limitações.

Cada resultado contém imagens das questões, `coordenadas_v3.json`, `diagnostico_v3.json`, `perfil_usado.json`, `avisos.txt` e `revisao/index.html`. Abra esse HTML no navegador para ligar camadas, selecionar páginas e consultar os motivos das marcações.

O detector permanece experimental: exige texto extraível, não inclui OCR e depende de regras compatíveis com o layout. Textos compartilhados e recortes devem ser revisados. A V3 reorganiza a rotina validada na V2; não acrescenta uma nova técnica de reconhecimento.

Para executar os testes sem criar cache Python:

```powershell
python -B -m unittest -v test_recorte.py test_extrator_v3.py
```
