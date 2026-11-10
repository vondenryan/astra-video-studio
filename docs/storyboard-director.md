# Director V2 — storyboard e revisão iterativa

O Director V2 usa planos tipados e determinísticos, sem exigir outro modelo ou serviço pago. O host interpreta objetivo, público, mensagem, restrições de marca e referências; o backend verifica os dados e executa ferramentas controladas. Os contratos antigos `scene_*` e `visual_review` continuam V1.

## Fluxo

1. Importe uma trilha com `audio_inspect` e crie tokens com `design_tokens_set`. Os tokens precisam das cores `background`, `foreground`, `accent` e da tipografia `heading`/`body`, com fontes instaladas identificadas exatamente.
2. Use `brief_validate` com `schema_version: 2`, objetivo, público, mensagem, restrições, tokens, trilha e de três a seis cenas. Cada cena declara intenção, título, texto e família `hero`, `split` ou `editorial`. Combine ao menos duas famílias; as três estão disponíveis. O teste de aceite combina as três.
3. `storyboard_plan` publica evidência imutável e devolve `plan_id`/`plan_sha256`. Consulte `operation_query(section="scenes")` para páginas limitadas. A resposta MCP continua compacta por padrão; `response_mode="full"` é explícito.
4. `storyboard_execute` recebe os dois identificadores e executa o plano uma única vez. Cria um AEP novo com composição principal e precomposições, texto editável, formas nativas, quatro técnicas, um estado de áudio novo e render H.264/AAC. Mantenha o MCP aberto enquanto o worker trabalha e consulte `storyboard_status(execution_id)`.
5. `review_samples_create` extrai frames de entrada, permanência, transição, saída e, nas revisões, do intervalo alterado. `operation_query(section="review_samples")` pagina caminhos e hashes. Só depois de realmente observar as imagens registre `storyboard_review`.
6. Para uma revisão pontual, use `storyboard_revise`, o hash atual do AEP e `rebuild_audio: true`. Exemplos completos: `Troque o título da cena 1 para "IDEIAS COM DIREÇÃO"` e `Trocar texto da cena 2 para "Ritmo com intenção."`. A gramática exige correspondência completa; não executa cláusulas extras ou instruções livres.

## Planejamento e limites

- Peças de 15–30 segundos, FPS inteiro de 12–60, resolução par até 1920×1920. O teto de render configurado continua aplicável; não são ampliados os limites de preview silencioso ou de áudio.
- A distribuição de cenas e a sobreposição de cerca de meio segundo usam frames inteiros. A leitura reserva ao menos dois segundos, ou palavras/3 + 0,7 segundo, excluindo entrada/saída. É uma heurística declarada, não prova de legibilidade ou ritmo.
- Hierarquia exige título maior que corpo; corpo tem pelo menos 16px. O contraste de texto/fundo precisa de 4,5:1. Tokens definem cores, tipografia, espaçamento e área segura. Fontes são resolvidas no AE antes de substituir um projeto limpo; overflow e geometria na permanência são verificados nativamente.
- Os assets visuais deste fluxo são texto e formas nativas gerados pelo plano. A trilha existente precisa cobrir a peça inteira; não há geração de música, looping implícito ou semântica automática de imagens. Importação de imagens/vetores continua disponível nas ferramentas de design e mídia, fora do construtor V2.
- As técnicas são slide de título, reveal do marcador da cena, scale do acento e fades nas precomposições. O reveal fica fora dos textos revisáveis para que uma troca de texto não seja cortada por uma máscara dimensionada para o conteúdo anterior.
- O áudio continua pós-produção FFmpeg, não é embutido no AEP. Uma revisão exige autorização explícita para construir um novo sidecar ligado ao novo hash, reutilizando a intenção e o asset fixados; não altera ou rebaseia estados anteriores. A faixa usada no aceite é um sinal sintético de teste, não uma trilha musical final.

## Proteções e evidências

Plano, referências observadas e trilha têm hashes. Alterações de tokens, relatório, amostras ou assets invalidam dependências. As anotações de referência registram autor, amostras selecionadas e observações; análise de metadados permanece separada da interpretação visual declarada pelo chamador.

Cada execução reserva uma tentativa exclusiva antes de enviar trabalho nativo. Falhas/resultados incertos ficam registrados; não se reenvia o plano, não se remove quarantine e não se reinicia o AE automaticamente. Cada evolução de execução publica uma evidência imutável; apenas o ponteiro atual muda. `storyboard_status` consulta o worker existente, sem refazer o trabalho.

Revisões usam o serviço de patches da Sprint 9, incluindo snapshot, hash atual, propriedade/dependências, verificação de todas as propriedades não alvo e reabertura antes da promoção. O projeto atual pode incluir edições compatíveis salvas fora do Director; trabalho manual não salvo deve ser capturado com `project_save` antes do planejamento. Não há reconstrução geral das cenas, substituição de keys ou escrita de JSX arbitrário. Patches de texto preservam estilos, âncoras e posição, portanto um conteúdo novo ainda exige revisão de composição.

O orçamento de uma a cinco revisões é compartilhado por toda a árvore da execução original. Uma tentativa nativa falha ou incerta também consome sua vaga; criar um ramo não reinicia o orçamento. Ao esgotar, pare para avaliação do operador. Não existe loop automático de tentativa artística.

Reviews têm severidade, categoria, descrição concreta, IDs de frames inspecionados e correção proposta. Uma nova review pode referenciar o hash de uma review com problemas da execução pai para registrar nova verificação. Evidências anteriores permanecem acessíveis; referências de outro vídeo, imagens modificadas e issues sem amostras inspecionadas são recusadas.

Frames observados, decode completo, audição/playback humano e aprovação artística são estados distintos. A API de review de frames não certifica audição nem reprodução completa. Adequação semântica à marca, musicalidade, composição e ritmo final dependem de avaliação humana. A pendência externa do Claude Desktop na Stint 9.3 continua independente; EffectCraft permanece adiado.
