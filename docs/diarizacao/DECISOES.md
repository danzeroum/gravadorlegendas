# DECISÕES — Diarização e Atribuição de Falantes

Continua a numeração de `docs/qualidade-audio/DECISOES.md` (D-001..D-016).
Formato: Contexto / Decisão / Alternativas / Consequências / Reverter.

---

## D-017 — Fan-out explícito: diarizador com fila própria e áudio sem RNNoise

**Data:** 2026-10-28 (UTC)

**Contexto:** `AudioManager` passava a mesma `multiprocessing.Queue`
(`_audio_queue`) ao `TranscriberProcess` e ao `DiarizationProcess`. Uma
`Queue` entrega cada item a **um** consumidor: com diarização ativa, o
Whisper perdia trechos e o diart recebia áudio picotado (ACH-01). Além
disso, o RNNoise (quando ativo) era aplicado antes de tudo, inclusive do
WAV usado no reprocessamento com diarização, e o fallback espectral degrada
a fala (D-009).

**Decisão:** `_diarization_audio_queue` separada; o `_fanout_loop` publica
em ambas. Diarizador ao vivo e WAV de reprocessamento (`_recorded_chunks`)
recebem o áudio **antes** do RNNoise (depois do mixer). O Whisper continua
recebendo o áudio filtrado, como antes.

**Alternativas:**
- Diarizador lendo do Whisper (encadeado): rejeitado — acopla os processos
  e o diarizador herdaria o atraso do Whisper.
- `multiprocessing.Manager` com broadcast: rejeitado — overhead e outro
  processo para gerenciar sem ganho sobre duas filas.

**Consequências:** o dobro de cópias de chunk quando a diarização está
ativa (~32 KB/s extra, desprezível). O WAV de reprocessamento deixa de ter
RNNoise.

**Reverter:** passar `_audio_queue` ao `DiarizationProcess` e remover o
bloco "Alimenta o diarizador" do `_fanout_loop`.

---
