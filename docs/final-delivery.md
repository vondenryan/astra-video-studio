# Sprint 11 — render final e pacote de entrega

## Escopo entregue

Quatro ferramentas novas levam o catálogo a65: render_presets_list, render_submit, delivery_collect e delivery_validate. Render final tem contrato próprio, separado das prévias silenciosas de15s e com áudio de20s. O motor continua After Effects25/Windows; EffectCraft permanece adiado.

| Ferramenta | Resultado |
| --- | --- |
| render_presets_list | Detecta encoders FFmpeg e publica dois presets; lista via operation_query(section=render_presets) ou full explícito. Detecção de software não prova template/alpha AE: isso depende do ACK e dos frames de cada render. |
| render_submit | Enfileira render final em destino novo, com hash AEP-base, FPS/resolução/intervalo/cor explícitos e áudio quando necessário. Retorna job_id; acompanhar por job_status e cancelar por job_cancel. |
| delivery_collect | Copia AEP/mídias/áudio/saída; relinka somente o AEP do pacote, salva/reabre e compara todas as composições/camadas inspecionadas. Publica manifesto com hashes e dependências. |
| delivery_validate | Confere arquivos/manifesto, abre o AEP coletado sem salvar, verifica links/fontes, decodifica toda saída e reconstrói o PCM usando apenas os áudios coletados. |

Não há executor genérico de script, shell ou filtro. Stdout continua protocolo; logs ficam separados. Respostas ricas seguem8KiB e consultas16KiB, com evidência completa preservada. Nenhuma configuração de aplicativos foi alterada automaticamente.

## Contrato do render

FinalRenderRequest exige project_id/composition_id, base_aep_sha256, fps, destination (diretório relativo ao workspace que ainda não exista) e color_policy=interpret_native_rgb_as_srgb. duration default30s, start_time default0, width/height default1920×1080. Campos desconhecidos/números não finitos são recusados.

Limites: fonte até3840×2160; resolução par, sem upscaling; FPS deve ser o da composição salva (sem retiming implícito). Intervalo quantizado em frames inteiros e contido na composição. Duração/frame count têm tetos de operador: ASTRA_FINAL_MAX_SECONDS60, ASTRA_FINAL_MAX_FRAMES1800, ASTRA_FINAL_TIMEOUT900s por padrão. Teto de configuração não garante qualquer combinação: fonte, áudio, frames, espaço e formato também precisam passar. Não elevar tetos para ocultar falha.

O orçamento antes de submissão/execução usa16bytes por pixel nativo +8bytes por pixel de saída, por frame, com margem256MiB. É estimativa conservadora, não tamanho real nem reserva de disco. Não há limpeza automática de versões para liberar espaço. Destinos existentes, escapes e caminhos absolutos são recusados.

Render final compartilha worker único/fila de quatro com as prévias. Captura cópia descartável de AEP/queue; fonte/queue do operador não são sobrescritas. preview-pending.json continua sendo a quarentena comum: timeout nativo mantém marker/outputs e não dispara outra execução/kill automático. O timeout maior é específico do render final e não altera o deadline60s da bridge ou o protocolo artifact-v1.

## Presets, cor e alpha

**h264_aac:** exige audio_state_sha256 ligado ao mesmo AEP-base. Imagem H.264/yuv420p8bit, áudio AAC192kb/s/stereo48kHz. Mixagem e limites de pico seguem Sprint10. Resolução usa fit/pad sem crop. RGB nativo é interpretado como sRGB por escolha explícita; conversão de matriz para BT.709/range limitado e tags de primárias BT.709/transferência sRGB IEC61966-2-1. Não chamar isso de conversão HDR, ACES/OCIO ou entrega broadcast de gamma2.4.

Admitimos projeto não linear de8bits com working space ausente (string nativa vazia/None) ou sRGB IEC61966-2.1. Outros espaços/linearização/profundidades falham antes de aerender; nenhuma preferência global de cor é alterada. Fonte/template/saída efetivos ficam registrados. Os campos de cor são conferidos no MP4 final; flags do encoder sozinhas não bastam. Os testes encontraram campos omitidos e passaram a definir também atributos por frame com setparams.

**tiff_rgba8:** sequência TIFF nativa com RGB+Alpha/8bit, na resolução da composição. Não permite resize, troca de associação ou depth implícitos. Usa o template instalado TIFF Sequence with Alpha e confere seus settings no ACK. Exige pixel format RGBA8 nos frames, copia cada TIFF byte a byte para frames/frame_00000.tif etc e verifica todos os hashes/decodes. sequence.json registra FPS/intervalo, cada frame/tamanho/hash, settings do output module, associação de alpha e background da composição.

O template desta instalação informa **Premultiplied (Matted)**. A associação é preservada: não anunciar PNG/alpha direto. Color do output module é read-only nessa instalação; a tentativa de mudá-lo foi recusada e preservada em evidência. Não aplicamos unpremultiply por suposição nem fabricamos transparência. Consumidores devem respeitar a associação/matte nativos registrados. Variantes não testadas do template/profundidade não são prometidas.

O canal alpha inteiro é decodificado para verificar contagem/dimensões e min/max; alpha_min<255 comprova pixels transparentes exercitados. Um arquivo RGBA todo opaco não vira “transparência testada” só pelo nome. A execução aceita verificou min0/max255 e seis frames reais de1080p. É prova de canal e preservação binária, não revisão artística de bordas em todos os cenários.

Vídeo e áudio têm decode completo; FPS/dimensões/frames/duração/rate/canais/início e picos são verificados. PCM é sample-peak, não true-peak/LUFS. A verificação genérica de streams não mede beats/cues; testes separados medem sincronismo. Sequência pode ter WAV separado se áudio solicitado; nunca áudio embutido nos TIFFs.

## Coleta de projeto

DeliveryCollect exige project_id, base_aep_sha256, render_job_id concluído de action render_final e destino relativo novo. Preview não é aceito como final. Projeto, fonte-base e render precisam coincidir.

1. Snapshot do AEP salvo, cópia de inspeção e ACK nativo de dependências, restaurando projeto do operador.
2. Recusa dependências ausentes/fora de raízes aprovadas e recursos não coletáveis: proxies, sequências de footage, PSD/AI em camadas, expressões armazenadas, Source Text animado/estilos truncados e plugins de disponibilidade não verificada.
3. Copia mídia de workspace/ASTRA_IMPORT_ROOTS e áudio original/PCM; mantém hashes antes/depois. Não adicionar raízes por pedido de ferramenta.
4. Na cópia do pacote, FootageItem.replace apenas para IDs e paths esperados. Compara interpretação da mídia e todas as composições/camadas inspecionadas antes/depois. Salva e reabre; links precisam apontar para mídias manifestadas dentro do pacote.
5. Copia saída verificada, publica manifesto e registra delivery_id. Falha mantém artefatos/diagnóstico; não promove versão do projeto original nem pacote incompleto.

Estrutura de distribuição: project.aep, media/, render/final.mp4 (ou sequência), audio/<asset-id>/source e analysis.wav, audio/mix.wav, audio/plan.json e manifest.json. O manifesto lista hashes/tamanhos, fonte/proveniência, cor, fonts/plugins, arquivos não coletados e ACK de reopen. O preset de alpha é entregue separadamente quando solicitado.

Fontes/plugins são **listados, não redistribuídos ou instalados**. A disponibilidade de fontes é verificada na máquina de validação; ausência é erro, não fallback silencioso. Isso não concede licença de redistribuição de mídias/fontes. A coleta atual é conservadora e inclui footage do projeto inteiro, não só da composição renderizada.

Áudio continua pós-produção. AEP sozinho não contém a trilha. audio/plan.json usa schema delivery_audio_v1, preserva o hash da fonte original e mapeia assets para paths relativos. Não é uma reescrita do AudioState original nem rebase automático para o hash novo do AEP relincado. A validação reconstrói o WAV pelo recipe/PCM coletados e exige identidade binária na toolchain local. Reimportar como projeto Astra com áudio continua exigindo criação explícita de novo estado ligado à nova versão.

## Validação e portabilidade

DeliveryValidate usa delivery_id registrado no workspace. Confere manifesto, conjunto exato de arquivos (inclusive recusa extras), sizes/SHA, ACK de reabertura do AEP e estado completo inspecionado; links/fontes; decode integral e recipe de áudio. Nada é relinkado/salvo durante validação. Falha de compartilhamento Windows na leitura do journal tem retry curto e limitado, sem repetir operação de serviço/native e sem aceitar JSON parcial.

ready_for_delivery é **verificação técnica local**, não aprovação de cliente. O teste reabriu o pacote no local coletado. Não há promessa de import automático do registro em outro workspace/máquina, nem teste de todos os relinks após mover diretórios ou de disponibilidade de fontes/plugins no destinatário. Abrir/validar pacote copiado em outro ambiente exige confiança na origem, dependências instaladas e nova conferência; não contornar a política de raízes.

## Evidência de08/11/2026

Regressão final:412 passed/15 skipped (57,51s). Aceitação nativa específica:1 passed em125,47s, executada separadamente com flag opt-in somente no arquivo de teste Sprint11. Os projetos anteriores foram preservados:1.150 AEPs gerenciados conferidos por hash. O novo AEP de teste ficou aberto; nenhuma aplicação foi terminada.

- [Aceite nativo completo](../workspace/sprint11-native-424560b9381d4a9d8c89fb81fafb3885/acceptance.json)
- [Log nativo aprovado](../workspace/sprint11-native-tests-v3.log)
- [Regressão final](../workspace/sprint11-functional-tests-v5.log)
- [Revisão das amostras](../workspace/sprint11-native-424560b9381d4a9d8c89fb81fafb3885/sampled-visual-review.json)
- [Pacote validado](../workspace/sprint11-native-424560b9381d4a9d8c89fb81fafb3885/package/manifest.json)

Distribuição:30s/1920×1080/24fps/720frames, AAC48kHz/stereo, dois eventos com erro observado0frames. TIFF alpha:seis frames em1080p, associação nativa preservada, min0/max255. Pacote:nove arquivos manifestados, AEP relincado/reaberto, mídia PNG local, Arial-BoldMT listado/disponível/não copiado e ADBE Fill listado como dependência nativa. Áudio reconstruído com identidade de PCM. MP4 SHA256 ac91f42976b80ed493e8f5df385472a762bff042f37446d7fdee1b8622b88435.

Foram realmente vistas três amostras do vídeo correspondente em0/15/29,9375s: quadrado cyan sobre fundo escuro na entrada, título FINAL DELIVERY cyan centralizado no meio e título quase invisível na saída. Nenhum clipping aparente nessas amostras. Não houve audição, playback integral humano ou aprovação artística. A fixture técnica não representa por si só motion profissional.

As tentativas anteriores com rótulo None não reconhecido e Color read-only são mantidas; falharam sincronamente, antes de seus respectivos renders, sem quarentena removida/reenvio incerto. O render1080p da segunda tentativa passou e permanece em evidência, embora o teste completo tenha parado no intermediário. A tentativa final foi nova e completa.

9.3 mantém pendência externa de três rotas no Claude Desktop; não é encerrada por estes testes. Sprint12 é a próxima implementação; EffectCraft permanece adiado. Recarregar MCP ocioso para ver65 ferramentas, sem reiniciar AE ou reenviar jobs.

Referências de implementação: [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html) e [ffprobe](https://ffmpeg.org/ffprobe.html); [Adobe FootageItem](https://developer.adobe.com/after-effects/uxp/after-effects-api/footageitem) para o contrato de substituição/preservação de interpretação, com comportamento efetivo comprovado no AE25.5 instalado.


### Fechamento do código final

A rodada final acrescentou prova de integridade do WAV opcional junto ao TIFF e de bloqueio de chamadas nativas do pacote quando há preview-pending.412 passed/15 skipped em57,51s; a fixture final exercita H.264/AAC, TIFF silencioso e TIFF com WAV separado. A imagem/template nativos aceitos não foram rerenderizados para esses guards de metadata.

[Validação nativa em leitura do código final](../workspace/sprint11-readonly-validation-76e5ab86a71441a888e85f4c00640fc3/acceptance.json) reabriu o pacote, refez todo decode/rebuild de PCM e confirmou pacote/fonte inalterados; não foi novo render. [Fixture FFmpeg final](../workspace/sprint11-fixtures-9c88be151da0437c8b37d1f2bef55c51/acceptance.json) é explicitamente sintética. Auditoria final:workspace/sprint11-acceptance-final.json.
