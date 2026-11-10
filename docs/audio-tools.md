# Sprint 10 — áudio e sincronização

## Escopo entregue

A Sprint10 introduziu seis ferramentas de áudio e chegou a61; o catálogo atual da Sprint11 tem65. A imagem e as keys continuam nativas/editáveis no AE; áudio, clipes, fades e marcadores ficam em **sidecars imutáveis para pós-produção FFmpeg**. Abrir só o AEP não reproduz essa trilha. Não há inserção de camadas/marcadores de áudio no AE, geração paga, novo motor ou alteração global de cor.

| Ferramenta | Contrato |
| --- | --- |
| audio_inspect | Importa cópia de áudio de raiz aprovada e verifica duração, codec, sample rate/canais originais, PCM normalizado, pico/RMS e candidatos de energia. Retorna asset_id. |
| audio_clip_set | Add/replace/remove de um clip_id em nova revisão de áudio; posicionamento/duração/fades em frames, trim em samples do PCM normalizado, ganho em dB. |
| audio_markers_create | Cues manuais por sample ou candidatos de subida de energia com confiança/incerteza; retorna marker_set_sha256. |
| timeline_markers_set | Append/replace_all de marcadores manuais por frame no sidecar, com IDs únicos; não grava markers no AE. |
| audio_sync_plan | Liga cues de clipes a keys de transformação salvas e produz estado candidato com deslocamento só dos clipes selecionados. Nunca move keys nativas. |
| audio_preview_render | Contrato separado até20s/900frames com áudio AAC estéreo; usa isolamento/fila de preview AE e mux/validação FFmpeg. |

## Fontes e unidades

Imports aceitos: WAV/MP3/AIF/AIFF/FLAC/M4A/OGG locais, até250 MiB e300s, uma stream de áudio sem stream de vídeo. Não aceitar caminhos fora do workspace/ASTRA_IMPORT_ROOTS, URLs, comandos ou filtros. Os originais ficam intocados. Containers com cover art classificada como vídeo podem ser recusados nessa versão.

Preservamos os metadados de rate/canais/codec originais. Para análise/mix, cada cópia é decodificada para **48.000Hz, estéreo PCM16**; FFmpeg faz resampling/downmix quando necessário. source_start_sample e cues referem-se a esse PCM normalizado, não ao clock original. Vídeo final usa H.264/yuv420p e AAC192kb/s estéreo48kHz. Ganho é explícito (-60..+12dB), sem normalização automática para esconder excesso de nível.

As operações de clip/timeline/sync exigem project_id, composition_id e base_aep_sha256 da **versão salva verificada**. audio_state_sha256 opcional inicia estado vazio; quando fornecido é o pai exato e imutável. Cada revisão guarda snapshot do AEP salvo e referencia assets/PCM/manifestos por hashes. Não há um head mutável de áudio: o cliente escolhe explicitamente o estado a usar. Branches anteriores continuam válidos para sua fonte-base.

Depois de uma revisão visual do AEP, um estado ligado ao hash anterior é recusado; não há rebase automático. Reconstruir uma nova revisão explicitamente a partir dos clips consultados/revisados. Estado manual não salvo no AE fica excluído, não é capturado nem descartado pelo áudio.

## Clips e cues

ClipSpec: asset_id, start_frame (default0), duration_frames, source_start_sample (default0), gain_db (default0), fade_in_frames/fade_out_frames (default0). Clips devem caber na composição e no áudio retido. Fades não podem se sobrepor. Até16 clips; sobreposição entre clips é permitida para mixagem. Add gera clip_id; replace/remove exigem ID existente e modo explícito. Replace preserva a ordem dos outros clips; nenhuma operação reescreve o pai.

Marcadores de fonte manuais: sample e label. Os IDs são gerados e aparecem em áudio/evidência completa. Timeline markers: marker_id, frame e label; até256 únicos. Fonte/timeline devem caber na duração. Append não substitui marcador existente; replace_all é explícito.

Energy usa janelas20ms, limiar RMS -24dBFS, subida aproximada9dB e separação120ms, até256 candidatos. A confiança é heurística, limitada a0,95; uncertainty_samples960 informa a resolução da janela. Não é detecção semântica de música, garantia de beat ou onset sample-exato. Cues manuais têm incerteza declarada0; a precisão depende da marcação fornecida.

## Planejamento de sincronismo

Cada binding inclui clip_id, marker_set_sha256, source_marker_id, layer_id, property e key_index. Propriedades permitidas: position/anchor/scale/rotation/opacity. A key vem da inspeção salva do AEP-base; tracks com expressão são recusadas. Cues devem pertencer ao asset/manifesto do clip e ao trecho retido. Alvos incompatíveis para o mesmo clip falham antes de snapshot/publicação.

O plano quantiza o novo start_frame pelo FPS (arredondamento para frame mais próximo), valida limites e informa error_frames calculado, <=1. Não altera a animação nem declara que houve observação visual/auditiva. Retorna plan_only=true e um audio_state_sha256 candidato; usá-lo explicitamente em audio_preview_render é a escolha da versão de áudio.

## Consultas e evidências

Respostas MCP continuam compactas<=8KiB e páginas<=16KiB. Não inserir arrays de clips/cues na resposta padrão. operation_query agora aceita audio_clips, audio_markers e sync_events:

- audio_state_sha256: clips e timeline markers do estado.
- marker_set_sha256: cues de fonte.
- evidence.sha256 da resposta audio_sync_plan: sync_events e resultado completo da operação.

IDs/hash retornados são distintos e não intercambiáveis. Evidência é content-addressed; nada aceita caminho de evidência arbitrário. Logs/job journals ficam completos. Assets e revisões não são removidos automaticamente; a retenção continua questão da Sprint13.

## Prévia e validação

preview_render silenciosa permanece<=15s. audio_preview_render requer audio_state_sha256 e base_aep_sha256, herda start_time/max_width e permite até20s, mantendo fonte<=4K, largura<=1920 e total<=900frames.20s portanto não é garantido em FPS que ultrapasse900frames. As duas rotas compartilham worker único/fila de quatro e cancelamento existente.

Antes da submissão, validamos fonte/estado/dependências; no worker, mixamos e verificamos o áudio antes de preparar a cópia AE. O AEP/queue usados no render são descartáveis; a sessão gerenciada é restaurada pelo template existente. Timeout nativo preserva preview-pending.json e não causa reenvio/kill/recovery automático.

PCM mix tem sample count exato para o intervalo e pico<=-1dBFS. Excesso falha com saída/log retidos: reduzir ganhos em nova revisão, sem normalização silenciosa. O vídeo silencioso isolado é muxado sem reencode de imagem. ffprobe verifica áudio AAC/48k/stereo, duração e início de streams dentro de1frame. Decode completo de vídeo/áudio é obrigatório. AAC decodificado deve ficar<=-0,1dBFS e duração até1frame do vídeo; padding do codec é documentado, não confundido com evento fora de sincronia.

Picos são **sample-peak PCM16**, não true-peak/LUFS; não há promessa de loudness broadcast ou medição intersample. O campo event_sync_measured=false da verificação genérica de streams é proposital: metadata de início não mede cues. Testes específicos medem eventos decodificados separadamente.

## Aceitação de 08/11/2026

Fixture MCP+FFmpeg:20s/320×180/24fps,480frames, trilha/dois SFX/fades; vídeo sintético e AEP fictício declarados. Pixels decodificados confirmam os frames dos flashes; cues AAC são comparados a esses tempos com tolerância<=1frame. Isso não é execução AE.

Aceitação nativa separada:20s/640×360/24fps,480frames; novo AEP e keys reais nos tempos3s/10s, duas cues por FFmpeg, erro observado0frames nos dois eventos, decode completo e pico AAC decodificado -15,105dBFS.1.138 AEPs gerenciados preexistentes mantiveram hashes. Nova versão ficou aberta; nenhuma sessão AE foi terminada. Bridge reativada manualmente pelo operador, sem repetição de -r.

- [Aceitação nativa](../workspace/sprint10-native-4367a34cc06c4190a10346d9cde94b87/acceptance.json)
- [Revisão das três amostras](../workspace/sprint10-native-4367a34cc06c4190a10346d9cde94b87/sampled-visual-review.json)
- [Log nativo](../workspace/sprint10-native-tests.log)

Foram realmente vistas as amostras0/10/19,9375s do vídeo correspondente: escuro/invisível no início, título centralizado visível no meio e escuro no fim. Não houve playback integral humano, audição nem aprovação artística. A peça é fixture técnica, não produto de motion profissional.

O áudio deste recurso é diferente de comissões históricas que sintetizaram/muxaram som fora da API: agora há ferramentas tipadas e aceitação própria. Sprint11 (>=30s/1080p/pacote final) foi entregue depois; ver [render final e entrega](final-delivery.md). EffectCraft está adiado por orientação do operador.9.3 mantém pendência externa no Claude Desktop; estes testes não a encerram.

Novas ferramentas exigem recarregar a conexão MCP quando seus jobs estiverem concluídos. Não reiniciar AE nem reenviar jobs incertos por atualização de schema.

Fontes de implementação: [filtros FFmpeg](https://ffmpeg.org/ffmpeg-filters.html) (atrim/afade/adelay/amix), [ffprobe](https://ffmpeg.org/ffprobe.html). Usamos filtros controlados/números validados, não expressões de filtro fornecidas pelo cliente.
