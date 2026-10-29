# DECISÕES — Extração de respostas de tela compartilhada

Formato: Contexto / Decisão / Alternativas / Consequências / Reverter.

---

## E-001 — OCR 100% local (Tesseract), só CLI, sem enviar nada para fora

**Data:** 2026-10-29 (UTC)

**Contexto:** gravações de reunião com a tela do OneTrust compartilhada
precisam virar uma tabela pergunta → resposta. O vídeo tem rosto e voz de
pessoas e dados da empresa; `AGENTS.md` proíbe enviar conteúdo a serviços
externos.

**Decisão:** `scripts/extrair_tela.py` + `src/screen_extract/`. Frames com
PyAV (sem ffmpeg/OpenCV novos) → recorte obrigatório (`--regiao`, tira os
rostos) → descarte de repetidos (fração de pixels mudados entre miniaturas
em cinza, para notar um "x" numa tela cheia) e borrados (variância do
laplaciano vs. mediana) → Tesseract `por` → caixa marcada por heurística em
numpy (borda quadrada à esquerda da linha + preenchimento do interior) →
consolidação do último estado por (pergunta, item), com casamento
aproximado (`difflib`) contra variações de OCR. `FrameReader` é um Protocol:
um leitor de visão pode entrar depois sem tocar no resto.

**Alternativas:**
- Hash perceptual global: rejeitado, não vê uma marcação de ~24 px.
- OpenCV para checkbox: rejeitado, dependência pesada para um quadrado.
- API de visão: fora de escopo (privacidade); fica para uma fase opt-in.

**Consequências:** só captura o que apareceu na tela; itens de lista não
rolada ficam de fora. Pergunta = linha sem caixa terminada em "?" ou
numerada; a pergunta "atual" atravessa frames (rolagem). OCR de texto pequeno
ou vídeo muito comprimido erra: conferir por amostragem. Nomes de arquivos de
saída: `audios/transcricoes/<nome>_tela.{json,csv,md}` (fora do git).

**Reverter:** apagar `src/screen_extract/`, `scripts/extrair_tela.py` e os
testes `test_screen_extract.py`/`screen_fixtures.py`.
