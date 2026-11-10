# Astra Video Studio — evolução para produção de motion profissional

**Versão:** 1.4
**Data:** 10 de novembro de 2026 (origem: 6 de novembro)
**Estado:** Sprints 0–13 tecnicamente implementados e otimização de criação entregue;77 ferramentas. Aceite externo das três rotas de edição Claude Desktop9.3 permanece pendente. Nova orientação do operador retomou a trilha EffectCraft: EC-0 iniciada, com primeiro marco de build/render CPU isolado verificado. Gates completos da EC-0 ainda pendentes; EC-1–4 e troca do backend padrão não estão autorizadas por esse marco. Fontes e limites em docs/test-report.md e docs/effectcraft/ec0-progress.md.
**Base:** MVP das Sprints 0–5, desenvolvido para After Effects 2025 no Windows.

## 1. Objetivo e uso deste documento

Evoluir o Astra de um MCP com cenas de modelo fixo para uma ferramenta capaz de construir, refinar e entregar peças de motion 2D com identidade visual própria, múltiplas cenas e áudio, preservando a editabilidade e o trabalho manual.

Este documento define requisitos, sequência de implementação e critérios de aceite. Sua criação não autoriza iniciar todas as etapas, alterar projetos de produção, instalar serviços ou contratar APIs. Uma solicitação posterior deve indicar a sprint a executar. Os comandos e nomes de ferramentas nas seções futuras são propostas de contrato, sujeitos à descoberta e validação no AE instalado.

O alvo inicial é uma peça de 15–30 segundos com três ou mais cenas, tipografia trabalhada, logo ou vetor, transições, trilha e efeitos sonoros, acompanhada de revisões pontuais e entrega do AEP com seus assets. Qualidade profissional será avaliada por evidências técnicas e revisão humana; não será prometida apenas por quantidade de recursos ou aprovação de testes.

## 2. Base existente que deve ser preservada

- Servidor MCP local via stdio; o MVP tinha 22 ferramentas e o estado atual documentado tem 55 após as Sprints 6–9 e Stint 9.1.
- Bridge serializada por dispatcher ocioso; confirmação explícita das execuções no AE.
- Criação de AEP, abertura de cópias, inspeção, snapshots e versões sem sobrescrever originais.
- IDs estáveis de composições e camadas, inclusive em projetos externos por mapeamento auxiliar.
- Camadas de texto, shape básico, sólido e mídia; importação local com cópia e hash.
- Transformações 2D, sete skills no MVP e oito no estado atual, stagger e batches com validação.
- Fill, Gaussian Blur, máscaras básicas e revelação de texto por máscara animada.
- Render isolado, MP4 silencioso, ffprobe, decodificação integral e amostras de frames.
- Director de cenas de 10–15 segundos com modelo visual definido, planos imutáveis e revisão limitada em português.
- Extração de metadados/frames de referências e registro explícito da revisão visual realizada.

A regressão de encerramento do MVP registrou **157 testes aprovados e 1 ignorado**, incluindo sete casos reais no AE. Esse resultado é histórico; as novas entregas precisam de evidência própria. Consulte `docs/test-report.md`.

### Limites atuais relevantes

O Director reconstrói sua própria cena em novas versões e recusa mudanças externas. As ferramentas atuais não substituem livremente keyframes ou expressões. Prévias têm até 15 segundos e 900 frames, origem até 3840×2160 e largura de saída até 1920, sem áudio. O processo MCP precisa permanecer aberto. O início manual da bridge foi necessário neste computador. Esses limites só devem mudar depois da implementação e validação correspondentes.

## 3. Princípios de implementação

1. Evoluir os módulos existentes; evitar reescrever a bridge ou quebrar os contratos públicos sem necessidade.
2. Manter a editabilidade nativa e o contrato AEP no backend AE. Avaliar editabilidade em IR/ecproj apenas na trilha EffectCraft, sem prometer roundtrip AEP ou substituir o contrato de entrega antes de aprovação específica.
3. Expor operações tipadas e delimitadas. Não oferecer execução genérica de JSX, shell ou expressões fornecidas pelo usuário.
4. Usar templates controlados e dados serializados; texto de briefing nunca deve virar código executável.
5. Preservar originais, snapshots e versões verificadas. Nenhuma falha pode promover silenciosamente uma versão incompleta.
6. Rejeitar alterações ambíguas. Uma revisão deve explicitar alvos, propriedades, intervalo e política de substituição.
7. Distinguir capacidade documentada, capacidade detectada, execução confirmada, verificação técnica, revisão visual e aprovação artística.
8. Continuar sem APIs pagas ou serviços obrigatórios. Dependências novas exigem justificativa, licença conhecida e instalação dentro do escopo autorizado.
9. Trabalhar uma sprint por vez. Não ampliar limites numéricos apenas para contornar uma falha.
10. Não automatizar cliques em diálogos nem encerrar o AE interativo como recuperação padrão.

## 4. Arquitetura proposta

| Componente | Responsabilidade futura |
| --- | --- |
| Scene Graph | Representar composições, camadas, fontes, relações, timing e dependências por IDs estáveis |
| Design System | Tipografia, cores, espaçamentos, safe areas, estilos e variantes de layout |
| Animation Editor | Ler e editar tracks, keyframes, easing, tangentes e trajetórias com escopo explícito |
| Revision Engine | Calcular um patch entre estado esperado e mudança solicitada, detectar conflitos e verificar o resultado |
| Director | Converter briefing/storyboard em cenas e operações permitidas, usando os componentes anteriores |
| Audio Pipeline | Importar, posicionar, mixar e validar trilha, locução e efeitos sonoros |
| Render Pipeline | Gerar prévias e entregas finais com presets detectados e validação técnica |
| Review Pipeline | Selecionar frames/intervalos, registrar problemas e acompanhar correções sem inventar observações |
| Job Manager | Persistir fila/estados e reconciliar processos e arquivos após interrupção |

A trilha EC propõe ainda um Scene IR versionado, EngineAdapter e worker Rust local sem GUI; esses componentes não existem hoje como abstração geral do Astra. ScenePlan não é um formato neutro completo. Consulte a seção 11.

Esses nomes descrevem responsabilidades. Não obrigam criar serviços separados. Reaproveitar `project_manager`, `motion_engine`, `director`, `media`, `jobs` e a bridge quando apropriado.

### Modelo de operação de edição

Toda mutação deve carregar: projeto e versão-base; alvos por ID; parâmetros validados; estado esperado das propriedades afetadas; política de conflito; identificação única da operação.

O fluxo será: ler estado → validar/prever mudança → criar snapshot → executar de forma serializada → salvar nova versão → reabrir/inspecionar → comparar alvos e estado não afetado → promover somente se verificado.

O plano pode conter várias operações, mas uma falha parcial deve ser identificada. Transação significa promoção controlada de arquivo/manifesto; não presumir que o AE oferece rollback completo de qualquer operação. Após falha, preservar os artefatos e exigir reconciliação do estado antes de continuar.

## 5. Roadmap

As quatro entregas principais estão divididas em oito sprints para manter cada etapa verificável. A numeração continua o MVP. Não há estimativa de prazo neste documento.

| Entrega | Sprints | Resultado |
| --- | --- | --- |
| Edição completa de cenas 2D | 6–7 | Composições livres, organização, tipografia e gráficos vetoriais |
| Animação e revisão precisa | 8–9 | Controle de curvas/keyframes e patches que preservam trabalho manual |
| Áudio e entrega final | 10–11 | Peças com som e arquivos prontos para entrega |
| Director avançado e robustez | 12–13 | Storyboard, revisão iterativa e recuperação de trabalhos |

### Sprint 6 — Composições e organização de cenas

**Objetivo:** permitir estruturar uma peça com várias cenas sem depender do modelo fixo do Director.

Implementar:

- Criar e configurar composições: resolução, FPS, duração e fundo.
- Criar precomps; inserir uma composição em outra; mapear seus IDs após salvar/reabrir.
- Duplicar, renomear, reordenar e remover camadas em cópias versionadas.
- Configurar início, entrada, saída e deslocamento temporal com precisão de frames.
- Criar nulls 2D; configurar/remover parenting com política explícita de preservação de transformações.
- Track mattes alpha/luma e blend modes em uma lista inicial detectada e testada.
- Inspecionar dependências e impedir ciclos de composição/parenting.
- Expandir a inspeção para verificar todas as propriedades novas antes de permitir sua edição.

**Ferramentas propostas:** `composition_create`, `composition_update`, `precompose_layers`, `layer_duplicate`, `layer_update`, `layer_remove`, `layer_parent`, `track_matte_set`.

**Aceite:** criar três cenas em precomps, organizadas em uma master de 20 segundos; usar null, parenting e uma matte; salvar/reabrir com relações e IDs corretos. Alterar uma cena sem modificar as outras. Remoção deve informar referências afetadas e recusar dependências não resolvidas.

**Fora do escopo:** câmeras, luzes e transformações 3D. Mudança de FPS precisa declarar se preserva segundos ou frames; não aplicar conversão implícita.

### Sprint 7 — Tipografia, shapes e identidade visual

**Objetivo:** construir layouts próprios, logos e gráficos além de retângulos/elipses preenchidos.

Implementar:

- Seleção de família/peso por identificadores reais de fontes instaladas, com diagnóstico de ausência.
- Texto de ponto e caixa; tamanho, tracking, entrelinha, alinhamento e estilos por intervalo quando disponíveis.
- Detectar overflow e testar textos longos, acentos e quebras de linha.
- Animadores nativos de texto por letra/palavra, começando por posição, escala e opacidade.
- Shape paths com vértices e tangentes delimitados; grupos, preenchimento, stroke e Trim Paths.
- Gradientes e morph entre paths compatíveis, condicionados à capacidade comprovada; incompatibilidade deve ser explícita.
- Fluxo de importação de vetor validado no AE instalado. Avaliar formatos efetivamente suportados; não presumir importação direta de SVG ou edição de qualquer arquivo Illustrator.
- Tokens de cor, tipografia e espaçamento; alinhamento/distribuição e safe areas configuráveis.
- Perfis de layout para paisagem, quadrado e vertical, com regras reais de reposicionamento.

**Ferramentas propostas:** `text_style_set`, `text_animator_apply`, `shape_path_set`, `shape_style_set`, `shape_trim_apply`, `layout_apply`, `design_tokens_set`.

**Aceite:** construir uma cartela de marca com logo/vetor, título, subtítulo e elemento desenhado por path; usar animação por palavra e Trim Paths. Adaptar o layout para 16:9 e 9:16 sem overflow nos casos testados. Verificar editabilidade, fontes e estilos após reabrir.

**Dependência:** Sprint 6. Importações não podem converter silenciosamente tudo em bitmap nem prometer vetores editáveis quando só houver footage importado.

### Sprint 8 — Edição avançada de animação

**Objetivo:** permitir refinamento da animação existente, além de adicionar presets.

Implementar:

- Inspeção de tracks com tempos, valores, interpolação, velocidades, influência e tangentes.
- Inserção, alteração, deslocamento e remoção de keyframes por propriedade e intervalo.
- Substituição explícita de trechos, mantendo keys fora do escopo.
- Easing temporal ajustável e trajetórias espaciais curvas com tangentes editáveis.
- Controle de continuidade nas fronteiras entre animações.
- Skills compostas de antecipação, overshoot, acomodação e sobreposição entre elementos.
- Retime de um grupo com política declarada para duração e arredondamento em frames.
- Motion blur por composição/camada, com parâmetros delimitados.

**Ferramentas propostas:** `keyframes_edit`, `easing_set`, `motion_path_set`, `animation_retime`; ampliar `motion_apply` e `motion_batch` sem quebrar chamadas existentes.

**Aceite:** refinar a entrada de um título já animado, alterar uma trajetória para curva e ajustar a velocidade, preservando a saída e as outras camadas. Comparar estados antes/depois, valores amostrados, curvas e frames de fronteira.

**Mudança deliberada de proteção:** a regra atual de não substituir keys continua como padrão. A nova API deve exigir política explícita, versão-base e estado esperado para substituir/remover keys. Expressões existentes continuam protegidas; sua edição não faz parte desta sprint.

### Sprint 9 — Revisão pontual e colaboração manual

**Objetivo:** revisar partes de uma peça sem reconstruir a cena inteira ou perder edições humanas.

Implementar:

- Patch tipado para conteúdo, estilo, transforms, timing e animação, usando as operações verificadas das Sprints 6–8.
- Prévia estruturada do que será alterado e das propriedades que serão preservadas.
- Detecção de conflitos por versão/hash e estado esperado das propriedades, incluindo mudanças manuais.
- Captura explícita do estado manual em nova versão antes de aplicar patches compatíveis.
- Recusa de patch ambíguo ou conflitante; não resolver divergências por sobrescrita silenciosa.
- Histórico de revisão com solicitação, patch, resultado e ligação entre versões.
- Retorno a uma versão anterior como uma nova versão, preservando o histórico.
- Adaptar o Director para emitir patches quando possível; reconstrução completa deve ser uma operação distinta e declarada.

**Ferramentas propostas:** `revision_plan`, `revision_apply`, `version_compare`, `version_restore`.

**Aceite:** um operador modifica manualmente uma cor e o layout de uma camada; após captura desse estado, uma revisão troca o título e atrasa a entrada em seis frames preservando as mudanças manuais. Um patch sobre uma propriedade modificada desde a versão-base deve falhar com conflito identificável.

**Limite de linguagem:** o host interpreta pedidos em operações tipadas. Parser local deve declarar seu vocabulário e recusar partes não entendidas. Não anunciar compreensão irrestrita de linguagem natural.

### Stint 9.1 — Respostas compactas e inspeção sob demanda (implementada)

**Estado:** implementada; regressão funcional de 312 testes aprovados e 12 ignorados. Evidência e limites em `docs/test-report.md` e `docs/compact-responses.md`. Sem nova execução/renderização no AE nesta etapa.

**Motivo:** o retorno integral do projeto em cada edição aumenta o consumo de contexto com camadas, keys e amostras repetidas. Uma medição local encontrou 1.265 linhas formatadas para três camadas e 3.908 para doze. Isso limita a interação com o modelo, sem demonstrar inviabilidade do filme no AE.

Implementar antes da Sprint 10:

- Resposta MCP/CLI compacta por padrão, com status, versão, identificadores, contagens, resumo e referência verificável à evidência completa. Modo `full` explícito para compatibilidade e diagnóstico.
- Manter integralmente as verificações internas e os registros de execução; compactação acontece somente na apresentação ao host.
- Referências imutáveis por hash dentro do workspace; leitura de evidências paginada e limitada em bytes, sem aceitar caminhos arbitrários.
- Inspeção por composição, camada, propriedade e seção. Keys e amostras somente quando solicitadas. Declarar se a consulta mostra a versão salva ou uma leitura atual do AE.
- Consultar jobs sem repetir todo o histórico e o estado completo do projeto a cada polling.
- Reutilizar os batches nativos existentes (`motion_batch`, `stagger_layers`, patches de revisão) para reduzir chamadas. Não criar um executor genérico de operações ou scripts.
- Medir respostas reais e fixtures com dezenas de camadas, comprovar tamanho limitado e conferir que a evidência completa e as proteções permanecem intactas.

**Aceite:** demonstrar via MCP real respostas compactas limitadas a 8 KiB, consultar camadas/keys/amostras por páginas limitadas a 16 KiB, obter o estado completo por opção explícita e recuperar evidência original por hash. Aumentar de 3 para 40/80 camadas não deve devolver listas integrais nas respostas de edição. Incluir testes de paginação, integridade, falhas e compatibilidade.

### Stint 9.2 — Transporte de evidência nativa volumosa

**Estado:** implementada e validada em leitura no AE real. O protocolo `artifact-v1` é o padrão: acknowledgement limitado a 8 KiB e evidência completa em arquivo do job limitada a 16 MiB, com identidade, byte count, SHA-256 e conteúdo conferidos antes da verificação/promoção. O modo antigo é explícito e mantém seus próprios limites. A estimativa de revisão passa a considerar os estados intermediários e keys geradas no canal de evidência. Mutex, quarentena, snapshots e verificações completas permanecem.

**Aceite observado:** resultado nativo acima de 2 MB transmitido com confirmação de cerca de 230 bytes; Unicode e hashes conferidos; falha conhecida preservada; projeto ativo e render pendente preservados. Não inclui novo render, edição de produção, teste nativo de 80 camadas ou garantia de prazo no máximo de 16 MiB. Contratos e evidência em `docs/native-result-transport.md` e `docs/test-report.md`.

### Stint 9.3 — Aceitação das respostas no host afetado

**Estado:** implementação/aceitação local entregues (370 testes aprovados,13 ignorados); operador confirmou política9.3 e consulta resumida de80 camadas (página3, next_offset3, sem arrays completos) no Claude Desktop. Aceitação externa das três rotas de edição ainda pendente; não encerrada. Medições, correções e roteiro em [aceitação host](docs/host-response-acceptance.md). Não reabre nem apaga aceites históricos9.1/9.2.

**Origem:** o review externo do Claude, datado de 08/11/2026, relata retorno integral repetido em layer_create, text_style_set e motion_apply, com mais de 1.800–2.000 linhas em quatro/cinco camadas. São contagens aproximadas de linhas; dez camadas é extrapolação. Não há payload/configuração suficientes para atribuir causa. Ver [análise e proveniência](docs/claude-response-review.md).

**Problema a resolver:** reconciliar o comportamento reportado com compact default já implementado. Não chamar isso de limite do AE nem pressupor que EffectCraft eliminará o custo de contexto.

Planejar/validar:

- Identificar executável/checkout e versão do processo MCP usado pelo host, schema anunciado e argumentos reais, incluindo response_mode. Conferir texto e structuredContent e qual conteúdo chega ao modelo.
- Comparar omissão do modo, compact explícito e full explícito nas três ferramentas citadas. Verificar rota antiga, processo não recarregado, cliente solicitando full ou apresentação fora do wrapper como hipóteses, não diagnósticos.
- Usar fixtures de 3/5/40/80 camadas, com keys, samples, máscaras e shapes; medir bytes exatos por resposta e acumulados, sem converter linhas em tokens por estimativa.
- Preservar evidência completa e verificação interna; manter consultas por hash e reutilizar batches tipados existentes. Não introduzir executor genérico nem descartar metadata para diminuir respostas.
- Se houver defeito, corrigi-lo com teste do caminho público; reload de MCP somente após conferir jobs ativos/pendências. Não reiniciar AE, reenviar mutação ou remover quarentena por esse motivo.

**Aceite:** no host afetado, resposta padrão/compact <=8 KiB por CallToolResult (texto + structuredContent), páginas <=16 KiB, sem keys/samples/listas completas de não alvos implícitas. Modo full somente explícito; evidência íntegra e consultável por hash. Registrar schemas/payloads/modo/versão, resultados de todas as ferramentas e origem fixture versus nativa. Teste local sem o host afetado não encerra o relato. A contagem de chamadas ainda deve ser controlada: tamanho por resposta limitado não torna contexto acumulado ilimitado.

**Dependências/limites:** diagnóstico read-only e fixtures primeiro; testes funcionais se houver mudança de código. Reproduções nativas mutantes exigem escopo próprio e proteção da sessão. Esta sprint foi iniciada por solicitação posterior do operador; testes desta entrega usaram fixtures e consultas de leitura, sem execução nativa no AE.

### Sprint 10 — Áudio e sincronização

**Estado:** implementada e aceita tecnicamente em08/11/2026:384 testes funcionais aprovados/14 ignorados; teste nativo específico1 aprovado. Prévia real20s/640×360/24fps com trilha/dois SFX/fades e erro medido0frames contra duas keys AE.1.138 arquivos AEP gerenciados anteriores mantiveram hashes. [Contratos e evidência](docs/audio-tools.md).

**Escopo de áudio:** FFmpeg pós-produção, com sidecars imutáveis ligados ao hash da versão salva; não há áudio/marcadores inseridos no AEP. Seis ferramentas entregues, incluindo audio_preview_render<=20s/900frames; preview_render silencioso mantém15s. Marcadores manuais/energia, sync de clipes sem mover animação, clipping recusado e decode completo. AEP sozinho não contém a trilha; pacote final é Sprint11. Samples vistos; audição, playback humano integral e aprovação artística continuam separados.

**Objetivo:** produzir peças com trilha, locução e efeitos sonoros sincronizados.

**Impacto EC:** mixdown/DSP existentes são candidatos a reutilização depois de EC-0; inspeção, APIs Astra, onsets/confiança, marcadores e QA continuam necessários. Áudio sintetizado/muxado em entregas avulsas não constitui esta API.

Implementar:

- Inspeção de duração, sample rate, canais e níveis dos arquivos aceitos.
- Posicionamento, recorte, ganho e fades; declarar se cada operação ocorre no AE ou na pós-produção FFmpeg.
- Marcadores manuais e extração opcional de eventos por energia/onsets, com confiança e limitações registradas.
- Associação de marcadores a eventos de animação sem mover trechos não solicitados.
- Mixagem e render de prévia com áudio.
- Verificação de duração, canais, níveis de pico e sincronismo em fixtures conhecidas.

**Ferramentas entregues:** `audio_inspect`, `audio_clip_set`, `audio_markers_create`, `timeline_markers_set`, `audio_sync_plan`, `audio_preview_render`.

**Aceite:** gerar uma peça de 20 segundos com trilha, dois efeitos sonoros e fades; sincronizar dois eventos visuais com marcadores conhecidos, com erro máximo de um frame nos testes. A prévia deve conter áudio decodificável e sem clipping nos limites definidos para o preset.

**Fora do escopo:** locução generativa paga, entendimento semântico de música e detecção perfeita de beats. Direitos de uso dos arquivos são responsabilidade do operador.

### Sprint 11 — Render final e pacote de entrega

**Estado:** implementada e aceita tecnicamente:412 testes funcionais aprovados/15 ignorados, teste nativo específico1 aprovado e revalidação final do pacote em leitura. Render nativo30s/1920×1080/24fps com áudio, TIFF RGBA8 com alpha decodificado, coleta e reabertura do AEP com mídia relincada e validação integral.1.150 AEPs gerenciados anteriores preservaram hashes. [Contratos/evidência](docs/final-delivery.md).

**Escopo:**65 ferramentas totais, presets H.264/AAC e TIFF RGBA8 nativo, tetos de render final configuráveis e independentes das prévias. Espaço de cor8bit não linear/sRGB explícito, sem retiming implícito. Alpha preserva associação nativa Premultiplied (Matted), não convertido para PNG direto por suposição. Áudio do pacote é sidecar/PCM/originais, não embutido no AEP; fontes/plugins listados sem redistribuição automática. Resultado técnico, samples vistos, audição/playback humano e aprovação artística permanecem distintos.

**Objetivo:** entregar material completo além da prévia curta.

**Impacto EC:** validar frames/alpha/intermediários e codecs existentes sem reconstruí-los. AEP continua contrato do adapter AE; pacote IR/ecproj exigirá schema, assets/fontes e reopen próprios, com aprovação do contrato de entrega. Não declarar roundtrip AEP sem perdas.

Implementar:

- Separar contratos de prévia e render final, mantendo os limites conservadores da prévia.
- Render final de pelo menos 30 segundos em 1920×1080, com áudio, no ambiente de aceitação.
- Presets descobertos e testados: H.264 com áudio para distribuição e ao menos um formato intermediário ou sequência com alpha quando disponível.
- Seleção explícita de resolução, FPS, intervalo e destino dentro do workspace.
- Detecção de espaço disponível, orçamento estimado e limites de duração/frames configuráveis.
- Política explícita de gerenciamento de cor, profundidade e alpha; registrar configurações de origem/saída.
- Validação integral de vídeo e áudio, dimensões, duração, frames e canais conforme o preset.
- Coleta de mídias utilizadas, cópia do AEP, manifesto com hashes e relatório de fontes/plugins necessários.
- Verificação de abertura do pacote e caminhos de mídia; informar assets não coletados.

**Ferramentas entregues:** `render_presets_list`, `render_submit`, `delivery_collect`, `delivery_validate`.

**Aceite:** entregar um pacote de 30 segundos com AEP, mídias, MP4 com áudio e manifesto; reabrir a cópia coletada, conferir links e decodificar todo o vídeo/áudio. Se alpha for suportado, comprovar o canal em um teste específico, não pelo nome do preset.

**Limites:** não prometer suporte a todos os codecs. Não copiar arquivos de fontes/plugins automaticamente; listar dependências e respeitar licenças. Não alterar a configuração global de cor do usuário silenciosamente.

### Sprint 12 — Director com storyboard e revisão iterativa

**Estado:** implementada e tecnicamente verificada em 2026-11-09; revisão artística humana pendente.

**Entrega:** sete ferramentas novas,72 totais; contrato V2 separado do Director legado. Storyboard imutável de três a seis cenas, três famílias de layout, tokens/contraste/tempo de leitura, trilha fixada, quatro técnicas, samples por fase e intervalos alterados, reviews imutáveis e patches textuais em português com orçamento compartilhado entre ramos. Assets visuais automáticos são texto/formas nativas; imagens/vetores continuam nas ferramentas existentes. Veja `docs/storyboard-director.md`.

**Evidência:** regressão final434 passed/16 skipped; aceite nativo1 passed/149,84s. Peça18s1280×720/24fps/432frames, três cenas e quatro técnicas, áudio AAC sintético de teste, duas revisões e edição compatível salva preservada.1.157 AEPs anteriores à tentativa final mantiveram hashes; a edição intermediária foi feita por ferramenta tipada, não por ação humana, e não amplia o aceite manual anterior da Sprint9. Reinspeção final em leitura confirmou o AEP atual e geometria nas três versões; amostras vistas e reviews posteriores registram correções/reverificações textuais. O review final marca sobreposição transitória de títulos no crossfade como ponto artístico para avaliação. Nenhum playback completo, audição humana ou aprovação artística foi declarado. Evidências em `workspace/sprint12-acceptance-final.json`; EffectCraft e aceite externo9.3 continuam independentes.

**Objetivo:** planejar e executar peças variadas usando as ferramentas já ampliadas.

**Impacto EC:** motor novo não substitui interpretação de briefing, storyboard, legibilidade, ritmo ou revisão humana. Render mais barato é hipótese a medir, não motivo para eliminar esta sprint.

Implementar:

- Briefing estruturado: objetivo, público, mensagem, textos, assets, duração, formato e restrições de marca.
- Storyboard com três ou mais cenas, intenção de cada cena, layout, transição e mapa de áudio.
- Pelo menos três famílias de layout distintas, combináveis e parametrizadas por tokens.
- Planejamento que considere duração de leitura, densidade de texto, continuidade e hierarquia.
- Análise assistida de referências por amostras e anotações; metadados e observação visual permanecem separados.
- Amostragem de entradas, holds, transições, saídas e intervalos alterados.
- Checklist com problemas específicos, severidade, evidências, correção proposta e nova verificação.
- Iteração por patches, com orçamento de tentativas e condição de parada para evitar loops.

**Ferramentas propostas:** `brief_validate`, `storyboard_plan`, `review_samples_create`; evoluir `scene_plan`, `scene_revise` e `visual_review` com contratos versionados quando necessário.

**Aceite:** produzir uma peça de 15–30 segundos com ao menos três cenas e quatro técnicas, áudio e identidade visual consistente. Executar duas revisões pontuais em português, preservando ajustes manuais e arquivos anteriores. Revisão humana deve avaliar legibilidade, composição, ritmo e coerência com o briefing.

**Limite:** sem modelo externo obrigatório. Compreensão rica pode ocorrer no host; backend continua executando planos tipados. Revisão automática não substitui aprovação artística, e frames não provam que o vídeo inteiro foi assistido.

### Sprint 13 — Persistência, diagnóstico e recuperação

**Estado:** implementada; aceite técnico e evidências em `workspace/sprint13-acceptance-final.json`. Quatro ferramentas novas,76 totais. Veja `docs/recovery.md`.

**Resultado:** regressão final462 passed/18 skipped; aceite nativo principal1 passed/72,93s e interrupção do host de uma leitura nativa confirmada1 passed/11,58s.1.162 AEPs anteriores preservados no teste principal;1.164 preservados nas leituras/conferência final. As quatro respostas novas ficaram entre1.829 e3.048 bytes no MCP real. Nenhuma exclusão, reenvio de mutação incerta ou encerramento do AE interativo. Aceite artístico, revisão das transições da Sprint12 e pendências externas permanecem separados.

**Escopo verificado:** fila persistente de quatro vagas entre processos, donos por PID/horário de criação, locks, fases/cancelamento, reconciliação sem reenvio, dependências e plano de limpeza sem exclusão. Interrupções controladas de build/render/encode usam helpers e confirmações sintéticas identificadas; o aceite nativo separado testa dependências, mídia ausente, render/cancelamento e queda do host após consulta real já confirmada. Somente consultas nativas confirmadas podem liberar sua quarentena por modo explícito; mutações e renders incertos continuam protegidos. Nenhum teste encerra o AE interativo.

**Objetivo:** tornar o fluxo previsível em sessões longas e após interrupções.

**Impacto EC:** estender ownership/reconcile a workers Rust, recursos e cancelamento sem apagar evidência. Proteções básicas são gate desde EC-0; não esperar esta sprint para controlar falhas.

Implementar:

- Fila e estados persistentes, com propriedade clara do worker e locks entre processos.
- Reconciliar jobs, processos nativos, acknowledgements e arquivos após reinício do host.
- Distinguir operação não iniciada, confirmada, concluída e de resultado incerto.
- Recuperar jobs somente quando for seguro; uma mutação com execução incerta não pode ser reenviada automaticamente.
- Cancelamento por estágio, com estados honestos e preservação de saídas parciais.
- Relatório de fontes, plugins e mídias ausentes, sem instalação/relink silenciosos.
- Protocolo de reativação da bridge após reiniciar AE, incluindo caminho manual quando necessário.
- Política de retenção e limpeza só de temporários de propriedade do job; snapshots/originais não entram em limpeza automática.
- Diagnóstico de espaço, processos ocupados, modal provável e incompatibilidade de capacidades.

**Ferramentas propostas:** `queue_inspect`, `job_reconcile`, `project_dependencies`, `workspace_cleanup_plan`. Limpeza efetiva deve ser separada do plano e respeitar o escopo autorizado.

**Aceite:** interromper o host em fases controladas de build/render, reiniciar e obter estado correto sem execução duplicada nem sobrescrita. Exercitar fila cheia, AE indisponível, erro de render, mídia ausente e disco insuficiente. Nenhum teste de recuperação deve encerrar o AE interativo do operador.

**Dependência transversal:** cada sprint anterior deve manter journals e estados compatíveis com recuperação; não adiar as proteções básicas até esta etapa.

## 6. Critérios técnicos comuns

Para cada ferramenta nova:

- Schema tipado com limites, valores finitos, IDs estáveis, política de conflito e erros acionáveis.
- Testes unitários de lógica não trivial e limites; integração MCP verificando input/output público.
- Teste real no backend correspondente para comportamento nativo, persistência e propriedades novas. AE permanece obrigatório para aceitar mudança do adapter AE; fixtures EC não substituem esse aceite e vice-versa.
- Comparação do estado anterior/posterior, com hashes dos arquivos preservados.
- Verificação específica das propriedades implementadas: metadados genéricos não bastam para paths, mattes, fontes, áudio ou curvas.
- Evidência visual ou auditiva quando necessária, com escopo e responsável registrados.
- Documentação de capacidade detectada, comportamento suportado e limitações.

Não criar testes que apenas reproduzam a implementação. Priorizar cálculos, conflitos, preservação, recuperação e resultados observáveis. Testes reais continuam sendo opt-in e usam fixtures descartáveis.

### Regressões obrigatórias

Manter a proteção a projetos não gerenciados, fontes originais e trabalho não salvo; UUIDs persistentes; bloqueio de expressões por padrão; serialização da bridge; quarentena após timeout; render isolado; distinção entre submissão e execução confirmada; logs separados do protocolo stdio.

A substituição explícita de keys da Sprint 8 é uma extensão versionada de contrato, não uma remoção geral das proteções existentes. Atualizar `AGENTS.md` e documentação quando a capacidade for efetivamente implementada e aceita.

## 7. Cena de referência para aceitação final

**Briefing:** peça de apresentação de uma marca fictícia, 24 segundos, 1920×1080, 30 fps, com logo local, três mensagens curtas e encerramento com chamada para ação.

| Trecho | Conteúdo e recursos |
| --- | --- |
| 0–6 s | Abertura com logo/vetor, Trim Paths e título por palavra |
| 6–13 s | Mensagem principal com shapes, hierarquia tipográfica e trajetória curva |
| 13–19 s | Segunda mensagem, precomp, matte e transição entre cenas |
| 19–24 s | Encerramento, chamada para ação e assinatura sonora |

Incluir trilha, efeitos sonoros, motion blur controlado, pelo menos uma mudança manual preservada e duas revisões solicitadas em português. Gerar também uma adaptação vertical após o layout paisagem estar aprovado.

### Checklist de conclusão

- [ ] AEP abre com composições, camadas, relações e keys editáveis.
- [ ] Assets usados estão no pacote ou identificados como dependências externas.
- [ ] Fontes/plugins ausentes são informados; não há substituição silenciosa.
- [ ] Texto corresponde ao briefing e não apresenta overflow nos layouts testados.
- [ ] Transições e movimento foram revisados em amostras relevantes.
- [ ] Revisões afetaram apenas o escopo declarado e preservaram mudanças manuais.
- [ ] Originais e versões anteriores mantiveram seus hashes.
- [ ] Vídeo/áudio completos passaram por validação técnica.
- [ ] Sincronismo foi medido nos eventos de referência.
- [ ] Uma pessoa assistiu à peça integral e avaliou ritmo, composição e som.
- [ ] Relatório distingue falhas técnicas, limitações e preferências artísticas.

O resultado técnico pode ser aprovado antes do resultado artístico. Não marcar a peça como aprovada pelo cliente sem aprovação explícita.

## 8. Fora deste ciclo

Câmeras/luzes 3D, partículas, simulações, tracking, rotoscopia, edição irrestrita de expressões, plugins arbitrários, geração de vídeo por IA, locução paga, colaboração simultânea no mesmo AE, painel próprio e operação remota multiusuário.

Esses recursos podem ter roadmap posterior. Não são pré-requisito para produzir motion 2D profissional.

## 9. Documentação e entrega por sprint

Atualizar `README.md`, `docs/architecture.md`, `docs/tool-contracts.md`, `docs/decisions.md` e `docs/test-report.md` conforme o comportamento realmente entregue. Criar guias específicos quando necessário.

Ao encerrar cada sprint, informar: funcionalidades implementadas; arquivos e contratos alterados; testes e seus resultados; IDs/caminhos dos artefatos; revisão visual/auditiva realmente realizada; limitações e pendências. Não anunciar recursos apenas planejados como disponíveis.

## 10. Próxima etapa e autorização

Por orientação posterior do operador, continuar as sprints do pipeline AE e avaliar EffectCraft depois. **Sprint11 foi entregue; Sprint12 é a próxima**, seguida de13. A proposta anterior9.3→EC-0 permanece histórica e não controla a sequência atual.9.3 conserva sua pendência de aceitação externa; os testes das Sprints10–11 não a encerram.

Esta entrega não iniciou Sprint12 nem EC-0. Implementar uma sprint por vez, inspecionando contratos atuais, preservando projetos/pendências e separando fixtures, execução nativa, revisão amostral e aprovação artística. Não reutilizar o antigo comando de Sprint6 nem tratar a conclusão do áudio como autorização automática para substituir o motor.

## 11. Trilha EffectCraft — validação e adoção condicionada

**Prioridade atual:** retomada por orientação explícita do operador em10/11/2026. EC-0 em execução isolada, começando pelo núcleo CPU. A avaliação original continua como referência histórica; este início não autoriza EC-1–4, migração ou substituição do backend AE.

### 11.1 Base de decisão

Ver [avaliação completa](docs/effectcraft/assessment-2026-11-08.md), [matriz de 40 requisitos](docs/effectcraft/compatibility-2026-11-08.csv) e [proveniência](docs/effectcraft/README.md). Referência upstream fixada: a41ff5015c6687db15a6f074a47b870b8f09fece, manifesto0.21.0/Rust1.95. Análise estática, sem build, execução ou benchmark. Upstream alpha; capacidades no código não são equivalência AE aceita.

Há composição, curvas, shaping, vetores, efeitos, render headless e import/export AEP reais. Os efeitos atuais Fill e Gaussian Blur têm implementação candidata; plugins de terceiros AE não são bloqueador deste escopo. Há limitações AEP fora do loss count, fallback de fonte e comentários de camada não exportados. Preservar AEP original e identidade independente. CLI headless depende de ui-egui na compilação: validar ausência de GUI no worker, sem remover a interface upstream.

### 11.2 Arquitetura-alvo proposta

Astra MCP/Python → planos/políticas/jobs → Scene IR versionado + EngineAdapter → adapter AE atual **ou** worker Rust privado local via stdio → crates EC engine/host/render/export, GPU opcional. Manter logs stderr/protocolo stdout, capacidades tipadas, confinamento e evidências por UUID/tamanho/SHA. Sem API HTTP remota, scripts genéricos ou fallback silencioso.

A — CLI: menor esforço para provas, startup/serialização e dependência UI a avaliar. B — crates: máximo reaproveitamento, mas não há binding Python direta/ABI estável comprovada. C — processo local: isolamento/recursos e evolução modular, com custo de IPC/recovery. Preferir B dentro de C como alvo; usar A inicialmente. Não reimplementar interpolador, texto, filtros ou render já adequados upstream.

IR próprio deverá explicitar UUIDs/dependências, tempo/FPS/frames, start/stretch e tempo local de keys, unidades de ease, textos/ranges/fontes por hash, paths, efeitos semânticos e cor/alpha. Não fingir ae_id, ecproj=AEP ou que ScenePlan atual já resolve isso. Preservar fonte exata, conflitos, snapshots, não alvos, planos imutáveis e promoção após save/reopen.

### 11.3 EC-0 — prova de conceito isolada

**Estado:** em execução. Primeiro marco verificado: worker CPU mínimo compilado sem frontends GUI no grafo alcançável, persistência/reabertura de fixture sintética, três renders determinísticos e encode/probe/decode independente. O restante dos gates abaixo continua pendente. Ver [andamento e evidências](docs/effectcraft/ec0-progress.md). Aprovar resultado desta sprint não troca backend padrão nem autoriza migração geral/distribuição comercial.

**Entregas:** build Windows x64 fixado e grafo mínimo sem GUI; commands estruturados de composição/texto/curvas/Fill/Blur; persistência e inspeção; frames headless integrados experimentalmente ao pipeline Astra; comparação AE/EC CPU, depois GPU/encoder nativo em provas separadas. Manter PNG → FFmpeg/ffprobe/decode como verificação independente inicial. API experimental opt-in e fixtures/cópias privadas; não alterar a sessão aberta.

**Fixtures:** texto point/box e ranges/animadores com fonte exata e missing-font negativo; Linear/Hold/Bezier temporal/espacial, boundaries e start/stretch; precomps/parent/mattes/blends; SVG paint order/morph/Trim; máscaras/Fill/Blur/alpha/cor; save/reopen/UUID/restore/conflito; dry-run AEP com perdas/limitações; stress3/40/80 camadas, nesting e1080p30/30s. A entrega existente de55 camadas/112 movimentos pode ser referência adicional em cópia, sem alegar playback/arte humana que não foi realizada. Áudio20s/dois SFX é prova separada, não conclusão da Sprint10.

**Gates propostos, congelados antes dos testes:**

| Dimensão | Critério |
| --- | --- |
| Independência | Render sem AE/janela; comprovar worker sem dependências GUI efetivas ou resolver o residual antes da adoção. |
| Integridade | Original/snapshots intactos; IDs/deps corretos; conflito recusado antes de escrita; não alvos e save/reopen verificados; timeout não promove/reenvia. |
| Host | Cumprir9.3: respostas<=8 KiB, páginas<=16 KiB, sem estado completo implícito; evidência completa preservada. |
| Animação | Frames/keys exatos conforme política; erro escalar absoluto/relativo1e-5 e espacial<=0,1px no subset aceito; flags e controles preservados. |
| Visual | PNG comparável, por ROI/frame SSIM>=0,99 e MAE<=2/255, bounds texto<=1px, alpha<=1/255 nos casos equivalentes; revisar todos os outliers e proibir fonte substituída/shape ausente/ordem errada/clipping. |
| Export | FPS/dimensões/frames corretos, duração até1frame e decode completo; áudio testado com sync<=1frame e sem clipping. |
| Desempenho | >=5cold/10warm, mediana/p95/RSS/VRAM, motor/encode/end-to-end separados; mesmo conteúdo/encoder. Gate proposto p95<=1,25×AE; ganho>=1,5× é meta não comprovada. |
| Memória/estabilidade | Budget inicial proposto<=4GiB RSS/worker para stress1080p, menor conforme RAM; VRAM conforme máquina; três renders CPU determinísticos no ambiente fixado, incluindo comparação1/múltiplas threads. |
| Licenças | SBOM/closure target/features e licenças efetivas completos antes da incorporação; notices, fontes, marca e codecs tratados. |

Os números são critérios propostos, não resultados. Mudança de tolerância exige decisão explícita justificada, não relaxamento após falha. Comparação global não pode esconder diferenças em texto/edges/objetos. GPU precisa resultado próprio; skip não conta como aprovação. Exigir corpus AEP presente nos testes correspondentes, incluindo EFFECTCRAFT_AEP_FIXTURES_REQUIRED=1.

**Licenças:** raiz MIT/Apache, 14 documentos git e22 versões registry foram examinados, não todo o lockfile de746 pacotes nem o binário futuro. Uso comercial depende de cumprir notices/fontes/marcas e avaliar codecs/patentes. Não concluir liberação jurídica geral nem ausência de copyleft em todo o grafo pela amostra.

**Saída:** relatório gate a gate; seguir experimentalmente, seguir com subset explicitamente restrito ou adiar. Guardar falhas. AEP import/export com loss count zero não basta: verificar limitações permanentes, fontes e identidade. Regressão funcional após mudança de código e testes nativos opt-in/sequenciais, sem matar AE nem limpar pendências.

### 11.4 Etapas posteriores, sem autorização de execução

| Etapa | Resultado e condição |
| --- | --- |
| EC-1 | Scene IR e adapter mínimo, feature flag, capabilities, worker/persistência/inspeção; somente após EC-0 e decisão específica. |
| EC-2 | Paridade do subset Sprints6–9, shadow renders, não alvos/revisões protegidos; novos projetos opt-in, sem promover entregas AE automaticamente. |
| EC-3 | Reutilizar áudio/export em Sprints10–11, com APIs/QA/pacote próprios e contrato de editabilidade aprovado. |
| EC-4 | Upgrades fixados, budget/filas/recovery/retention alinhados a13. Guardas mínimas desde EC-0. |
| Adoção | Default EC para novos projetos só após aceites e autorização. Legado AEP continua AE quando necessário; migração individual opcional por cópia/dry-run/whitelist/diff visual e semântico. |

Rollback preserva versões e retorna ao último manifest AE verificado. Não editar planos/evidências históricos, converter originais, alterar comentários de clientes ou manter sync bidirecional automático. Projetos EC/AE são ramos com proveniência explícita.

Sprints10–13 continuam necessárias: mixer/codec upstream não entrega workflow, Director, arte nem robustez Astra. 3D/partículas/tracking e operação remota não são antecipados por esta decisão. Atualizar novamente o roadmap conforme evidência efetivamente produzida.

## Revisão de eficiência e qualidade — 2026-11-10

Solicitação do operador: otimizar chamadas/informação e acelerar criação sem perder qualidade; melhorar SFX e suavidade da segunda cena. Diagnóstico, evidências e contratos em [revisão de criação](docs/creation-optimization.md).

Implementado: `layers_create` com1–20 novas camadas/tipografia numa versão verificada;77 ferramentas. Resposta opcional `receipt`<=3KiB com resolver local por hash, mantendo compacto padrão/full legado e verificações internas. Ensaio inicial:8 chamadas/37,39s →1/4,69s para cinco camadas; primeiro frame da fixture idêntico após decode. Resultado reconstruído das70 respostas históricas:14,66MB full →104KB receipt. Sem claim de tokens, captura histórica do fio ou velocidade total do vídeo. Roteiro atualizado para37 chamadas por contagem estática; build completo otimizado ainda não executado.

Prioridades seguintes, com critérios de qualidade:

1. Curvas temporais: receita de aceleração/chegada Bezier com velocidade não nula em passagem; medir amostras próximas das chaves e comparar preview. Preservar guards, tangentes/boundaries e não alvos.
2. SFX: variantes por função, ataque mais suave e mix menos dominante; sincronismo verificável e A/B com a trilha. Curadoria/aprovação auditiva necessárias, sem confundir pico seguro com qualidade sonora.
3. Perfil de tempo por etapa e benchmarks repetidos antes de metas gerais; depois avaliar lotes tipados de paths/estilos/áudio e custo das definições de ferramentas. Nunca acelerar removendo confirmação, snapshots ou verificação de integridade.

As revisões artísticas do VÉRTICE não foram aplicadas nesta otimização. Paisagem ainda requer aprovação explícita antes da adaptação vertical. A orientação posterior de10/11 retomou EC-0 de forma isolada; Claude Desktop9.3 continua com rotas de edição externas pendentes.
