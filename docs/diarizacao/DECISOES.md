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

## D-018 — Diarização de arquivo com pyannote.audio; diart só no streaming

**Data:** 2026-10-28 (UTC)

**Contexto:** `DiarizationProcess.diarize_file` usava o
`OnlineSpeakerDiarization` do diart com `AudioFileSource` — pipeline de
streaming aplicado a arquivo, sem `num_speakers` nem modo exclusivo, embora
o README prometesse `pyannote/speaker-diarization-3.1` (ACH-02).

**Decisão:** novo `src/audio/offline_diarizer.py` (`OfflineDiarizer`) com
`pyannote.audio.Pipeline`. `diarize_file` delega a ele mantendo o retorno
`list[dict]` (R6). Detalhes:
- compatível com 3.x (`use_auth_token`, saída `Annotation`) e 4.x (`token`,
  `DiarizeOutput.exclusive_speaker_diarization`), verificado contra a API
  do pyannote.audio 4.0.7 instalado;
- modelo padrão pela versão instalada: `speaker-diarization-community-1`
  no 4.x, `speaker-diarization-3.1` no 3.x (`DIARIZATION_MODEL` sobrepõe);
- áudio passado em memória (waveform + taxa), sem depender do decodificador
  de arquivos do pyannote;
- token: `HF_TOKEN`/`HUGGING_FACE_HUB_TOKEN` ou login salvo do
  `huggingface-cli` (o README já orienta `huggingface-cli login`); nunca
  aparece em mensagem de erro;
- cache em `~/.cache/gravador/audio/diarization` (o mesmo do
  `scripts/setup_audio_models.py`);
- modo exclusivo próprio (`make_exclusive`) quando a versão não fornece.

**Alternativas:**
- Manter diart para arquivo: rejeitado — não é o modelo offline e não
  aceita nº de falantes.
- Exigir pyannote 4.x: rejeitado — quem tem 3.1 instalado e termos aceitos
  continuaria funcionando sem migrar.

**Consequências:** reprocessar e importar arquivos passam a usar o modelo
offline. O modelo community-1 exige aceitar termos próprios no HF (além dos
do 3.1). Sem token, a mensagem diz exatamente o que fazer.

**Reverter:** restaurar o corpo antigo de `diarize_file` (diart) e remover
`src/audio/offline_diarizer.py`.

---

## D-019 — Falante na legenda: `[Nome] texto` em SRT e VTT, `Nome: texto` no TXT

**Data:** 2026-10-28 (UTC)

**Contexto:** `CaptionSegment` não tinha falante (ACH-08). O WebVTT tem a
voice tag `<v Nome>`, mas vários players a escondem — o nome sumiria
justamente onde o usuário quer vê-lo.

**Decisão:** `CaptionSegment.speaker: str | None = None` (fora do
desempacotamento posicional). Exportador com `speaker_names` (rótulo → nome
do speaker map): SRT e VTT com prefixo `[Nome] `, TXT com
`[HH:MM:SS] Nome: texto`. Sem nome mapeado, usa o rótulo. Sem falante, a
saída é byte a byte a antiga.

**Alternativas:** `<v Nome>` no VTT — rejeitado pela visibilidade.

**Consequências:** legenda com nome visível em qualquer player.

**Reverter:** remover `speaker_names`/`_caption_text` do exportador.

---
