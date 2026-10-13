# Extrator de questões: versões separadas

- `versao1/`: recorte por coordenadas da IA, em JSON ou coladas no console.
- `versao2/`: versão anterior de detecção local, com perfis e revisão.
- `versao3/`: versão atual organizada, com pastas separadas de entrada e saída.
- `historico/`: resultados, PDF de teste e temporários gerados anteriormente, preservados fora das versões.

Cada versão tem seu próprio código e dependências. Para usar a atual:

```powershell
cd versao3
python -m pip install -r requirements.txt
python extrator_v3.py
```

Coloque novos PDFs em `versao3/entradas`. Os resultados futuros ficam em `versao3/saidas`. A V3 foi entregue sem PDFs de teste ou resultados antigos. Veja `versao3/README.md`.
# Editor web local de perfis

O arquivo separado `gerador_perfis.py` usa o detector da V3 e abre uma interface no navegador. Execute na pasta principal:

```powershell
python -m pip install -r versao3/requirements.txt
python gerador_perfis.py
```

Carregue um perfil ou clique em **Novo perfil**, escolha um PDF e ajuste os campos. Os modelos de numeração preenchem as expressões automaticamente. **Testar perfil** recalcula a detecção em todas as páginas; selecione uma página para conferir as camadas e clique nas marcações para consultar os motivos. Para preencher limites ou alinhamentos visualmente, escolha o ajuste e clique na página; teste novamente para atualizar os cortes.

**Salvar perfil** grava em `versao3/perfis/` e pede confirmação antes de substituir um perfil existente. **Baixar JSON** exporta uma cópia. **Gerar imagens das questões** processa com os valores atuais, salva em `versao3/saidas/` e oferece um link para a revisão completa. As saídas anteriores são preservadas.

Mantenha o terminal aberto durante o uso e pressione Ctrl+C para encerrar. O servidor atende somente no computador local. Para mudar a porta: `python gerador_perfis.py --porta 8766`. PDFs enviados pelo seletor ficam numa pasta temporária durante a sessão; perfis e resultados salvos permanecem. Arquivos grandes podem ser abertos pelo caminho completo. O editor mantém as limitações da V3: exige texto extraível e não inclui OCR nem edição individual dos recortes.

