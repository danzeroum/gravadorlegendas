---
description: Dá nomes aos participantes de uma transcrição (ex. XPTO A=Juliana B=Daniel)
---
Renomeie os participantes conforme "$ARGUMENTS". O primeiro termo é o nome do
áudio/transcrição; os demais são pares como `A=Juliana`. Se vierem em texto
livre ("o A é a Juliana"), converta para pares. Rode
`.venv/bin/python scripts/transcrever_audio.py --renomear <nome> <pares>` e
confirme os arquivos atualizados.
