# Astra Video Studio PRO — avaliação do EffectCraft

Data: 8 de novembro de 2026. Estado: análise para decisão; integração não implementada.

## Parecer

**Recomendo aprovar uma prova de conceito isolada, sem substituir agora o backend After Effects.** O EffectCraft tem implementações reais de composição, animação, texto, efeitos e renderização headless. É plausível criar um Astra que produza novos projetos sem AE em tempo de execução. Ainda não há evidência para prometer equivalência visual, estabilidade de produção, desempenho superior ou migração geral do legado.

A arquitetura recomendada mantém o MCP/Python do Astra e acrescenta um **worker Rust local privado, sem GUI**, usando os crates do EffectCraft. Um modelo de cena próprio e versionado separa os contratos do Astra dos structs internos do motor. AE permanece para legado e comparação durante a transição. A ausência de plugins Adobe de terceiros não bloqueia o escopo atual.

A CLI ajuda a validar rapidamente, mas executa headless enquanto declara dependência de compilação em `effectcraft-ui-egui`. Não abrir janela e não incluir GUI no backend são critérios distintos. Não é necessário apagar a interface do repositório original.

## 1. Escopo e método

O pedido adotado é o texto anexado pelo operador, incluindo aguardar aprovação antes de modificar o projeto. Documentos e código externos foram tratados como evidência, não como autorização operacional.

Foram inventariados estruturalmente os 44 módulos Python/JSX do Astra e examinados fluxos transversais de criação, edição, identidade, inspeção, promoção, respostas e renderização, confrontando código, documentos técnicos e roadmap. Foram registrados 63 hashes de arquivos de implementação/documentação. Isso não equivale a uma auditoria linha por linha de toda a base.

O EffectCraft foi analisado em checkout fixado em **`a41ff5015c6687db15a6f074a47b870b8f09fece`**, commit de 08/11/2026. O manifesto declara workspace 0.21.0, edição Rust 2024 e toolchain mínima 1.95; não se deduz disso uma release estável. O inventário cobre 38 manifests locais de crates/apps e 746 pacotes do lockfile. Esse lockfile inclui todo o workspace, não somente o futuro worker mínimo.

Foi feita análise estática de fonte e documentação primárias e verificação de licenças efetivas selecionadas. **Não houve build/execução do EffectCraft, benchmark, render comparativo, teste de GPU, importação AEP ou testes de codecs.** Não houve alteração funcional Astra nem reexecução de sua suíte. Resultados históricos são identificados como tal. Não foi operado o AE nesta avaliação.

Os entregáveis ficam fora da pasta do Astra; o roadmap operacional permanece inalterado. A seção 10 é uma proposta para aprovação.

## 2. Diagnóstico da arquitetura atual

### 2.1 Fluxo e representação

Host/Codex → MCP Python local stdio → schemas/serviços tipados → JSX gerado por templates controlados → dispatcher ocioso no AE → inspeção nativa → verificação → nova versão AEP e manifesto. Preview usa AEP/queue descartáveis, aerender em processo separado, sequência de imagens, FFmpeg H.264, ffprobe e decode integral.

Há 55 ferramentas. A interpretação ampla de linguagem acontece no host; o Director local usa planejamento determinístico e vocabulário limitado. O backend não contém por si só um sistema geral de geração por IA.

`ScenePlan` não é um formato universal de projeto: descreve sobretudo cenas pertencentes ao Director. Projetos existentes e edições dependem de inspeções AE, AEP e metadados nativos. **Não basta substituir BridgeRunner.**

| Componente | Dependência e impacto |
|---|---|
| project_manager.py / existing_projects.py | `.aep`, save/reopen, fonte salva, inspeção e promoção. Precisam de tipos de artefato e adapter. |
| project_identity.py | UUIDs/comentários de projetos Astra e sidecars UUID ↔ ID persistente AE em projetos externos. EC precisa de mapa próprio, sem fabricar ae_id. |
| layers.py / scene_editing.py | Campos/matchnames nativos, parenting, matte e inspeção. Regras de dependências podem permanecer; acesso ao estado muda. |
| animation.py / motion_engine/service.py | Tracks, enums e confirmação AE. Tempo/unidades, flags e verificador precisam de tradução. |
| design.py / svg.py / treatments.py | Fontes PostScript, ranges UTF-16 AE, bounds, paths, efeitos e operadores. Métricas/render mudam. |
| revisions.py / director.py | Política conceitualmente reutilizável, execução e promoção dependentes de AEP. Histórico não deve ser reinterpretado. |
| ae_bridge e scripts JSX | Descoberta, bootstrap, fila, mutex e protocolo são específicos do adapter AE. Não são scripts EC reutilizáveis. |
| media/preview.py | Prepara AEP/queue e aerender. Deve delegar produção de frames por backend. |
| responses.py / jobs.py / media/ffmpeg.py | Boa base para compactação, journals e validação independente; alguns caminhos/registros ainda precisam generalização. |

### 2.2 Contratos a preservar

- Workspace/raízes de importação explícitos; sem shell, JSX arbitrário ou escrita livre expostos pelo MCP.
- Snapshot antes de mutação; nova versão e promoção apenas depois de inspeção/roundtrip e comparação de todos os não alvos.
- UUID estável e mapa sem roubo de identidade por duplicação/reordenação; comentários de clientes não reescritos.
- Expressões protegidas; edição com modo/janela/boundary, hash da fonte e estado esperado. Ferramentas antigas não sobrescrevem keys.
- Planos de revisão imutáveis, aplicação no máximo uma vez, captura explícita de mudanças manuais compatíveis, histórico de falhas preservado.
- Resposta MCP compacta até 8 KiB e páginas de consulta até 16 KiB, hashes estáveis e keys/samples explícitos, sem repetir toda a cena em cada chamada.
- No AE, artifact-v1: ACK até 8 KiB e evidência separada até 16 MiB; UUID/status/tamanho/SHA/JSON completo conferidos antes de liberar pendência. Deadline de 60 s não cresce com tamanho.
- Timeout não autoriza reenvio, remoção de pendência, promoção ou matar AE. Resultado desconhecido permanece em quarentena.
- Metadata/render executado, amostras efetivamente vistas e aprovação artística humana são categorias distintas.

### 2.3 Funcionalidades efetivas

Transformações 2D; oito skills e batch/stagger; composições aninhadas/nulls/parenting; mattes alpha/luma e inversos; blends Normal/Multiply/Screen/Add; edição protegida de curvas; point/box text, estilos por intervalos e animadores chars/words; paths/morph compatível/Trim Paths; SVG restrito; tokens e layouts responsivos; máscaras Add/Subtract, feather/opacidade/inversão e text reveal.

Os efeitos tratados explicitamente são **Fill (`ADBE Fill`) e Gaussian Blur 2 (`ADBE Gaussian Blur 2`)**. Não há dependência atual de plugins comerciais de terceiros. Projetos externos podem conter recursos opacos: preservar o AEP binário não prova extração nem portabilidade de tudo que ele contém.

### 2.4 Evidência existente

A documentação registra regressão recente com 361 testes passando e 13 ignorados; a aceitação read-only nativa 9.2 é separada. A aceitação nativa anterior de Sprints 0–9 registra 298 passando e um ignorado. São evidências históricas, não testes executados por este estudo.

A entrega documentada `workspace/deliveries/astra-asset-studio-20261108` tem filme de 30 s, 1920×1080, 30 fps/900 frames; nove composições, 55 camadas e 112 movimentos. Picture é AE; áudio foi sintetizado/muxado fora da API de áudio Astra. Isso não conclui automaticamente Sprints 10–11.

Um primeiro render tecnicamente válido foi rejeitado visualmente por ordem de pintura SVG. A correção manteve geometria nativa. Samples finais foram vistos; playback integral, audição e aprovação artística humana são separados. Essa entrega pode virar referência comparativa em cópia, após completar revisão, sem presumir aceite integral que ainda não ocorreu.

## 3. EffectCraft: arquitetura real

### 3.1 Workspace, Session e headless

A organização separa tempo/geometria/cor; raster/path/keyframe; projeto/texto/efeitos; render/media/expr/export/GPU/AEP; engine; host/script; automação e apps. Engine organiza Session/comandos. Host conecta mídia, expressões, export e scripting. Engine/render não declaram egui.

A CLI tem comandos estruturados, run/render e MCP headless. Run aceita JSON/JSONL com limites de tamanho/quantidade; saída JSON pode ser compacta e progresso vai para stderr. CPU é o default; `--gpu` solicita adapter headless e pode falhar sem hardware utilizável.

O manifesto CLI inclui ui-egui incondicionalmente, usado também em benchmark de UI. Não foi encontrada feature que isole essa dependência. Worker próprio com crates core é a direção para build sem UI, mas o grafo transitivo por target/features precisa ser comprovado. Evitar build de todo o workspace.

Não foi localizada binding Python ou ABI C estável. Consumo como biblioteca Rust é natural em programa Rust, não importação direta no Python. FFI adicionaria empacotamento/ABI e compartilharia falhas; processo privado é preferível inicialmente.

### 3.2 Projeto e tempo

Project tem itens, Comp/Layer e árvore de propriedades com IDs numéricos. `.ecproj` é JSON versionado com schema/escritor; `.ecprojx` também existe. Sharing com Arc e undo ajudam execução, mas não substituem contratos Astra. Writers antigos podem perder campos futuros desconhecidos.

Tempo usa i64 com **254.016.000.000 ticks/s** e FPS racional. Keys são locais à camada; o JSX atual recebe segundos de composição. É obrigatório converter start/stretch/remapping. Frames inteiros continuam canônicos nas operações Astra correspondentes.

### 3.3 Curvas e expressões

Há Linear/Hold/Bezier, velocidade/influência por dimensão, tangentes espaciais, flags auto/continuous/roving e tabelas de comprimento de arco. Influência EC usa fração 0–1, Astra percentuais. Defaults de influência/spatial-auto precisam ser explicitamente sobrescritos conforme o estado esperado.

Reusar esse interpolador evita reconstrução. Ainda é preciso comparar curvas manuais, overshoot, boundaries e intervalos adjacentes. Boa/JavaScript e objetos inspirados no AE não equivalem a ExtendScript, File/app/scheduleTask ou enums host. Não portar JSX por simples execução; manter expressão protegida no subset inicial.

### 3.4 Texto, paths e efeitos

Texto usa harfrust/skrifa, bidi, linebreaking, glifos vetoriais, estilos por runs e animadores/seletores. A cobertura é relevante, mas métricas, tracking/leading, seleção e bounds precisam de comparação com fonte idêntica. Face IDs são locais ao processo. O resolvedor pode usar Inter quando a fonte não existe, além de fallback por caractere: Astra deve bloquear substituição não aprovada com preflight e hash da fonte.

Paths, fill/stroke, Trim Paths, morph e SVG existem. O importador mais amplo não autoriza relaxar o subset estrito Astra ou rasterizar silenciosamente recursos. Winding, ordem de pintura e operadores merecem fixtures específicas.

Existem EffectSpecs com IDs/parâmetros e implementações reais de `ec.generate.fill` e `ec.blur.gaussian`, incluindo blur/dimensões/repeatEdge; há mapas ADBE. Catálogo amplo não prova pixels equivalentes. Fill não declara GPU na spec inspecionada: composição acelerada não significa todos os efeitos acelerados.

### 3.5 Cena, render, GPU e áudio

Comp aninhada, parenting, mattes, máscaras, vários blends e recursos 3D/câmeras/luzes aparecem implementados. 3D é maior que o escopo atual e deve ser avaliado separadamente, sem bloquear o subset 2D.

Raster CPU usa RGBA premultiplicado f32, admitindo HDR. Cache de camadas tem orçamento/reutilização; há cache de disco opcional e pooling GPU. wgpu pode usar diferentes backends; CPU e readbacks continuam relevantes. Não foram medidos D3D12/Vulkan nesta máquina.

Export paraleliza frames por Rayon em lotes de 2–16 conforme threads. Estimativa de buffer: 1080p RGBA f32 =31,64 MiB/frame; 16 frames ~506 MiB antes de intermediários/cache/VRAM. 4K =126,56 MiB/frame. São cálculos, não medições RSS; justificam orçamento e backpressure.

Exportadores de imagens/vídeo/áudio, alpha/intermediários e mixdown estão presentes. H.264/ProRes/AAC usam FilmCraft fixado; outros codecs têm crates próprios. FFmpeg não é o renderizador interno upstream. Primeira PoC deve usar frames EC → FFmpeg Astra, mantendo um oráculo independente. Encoder EC vem depois.

Cor, linearização, premultiplicação, shutter e YUV afetam fidelidade. Comparar PNG primeiro; só MP4 mistura motor e codec. Cancelamento upstream pode apagar parciais: usar job privado e adequar retenção Astra antes de permitir cancelamento em produção.

### 3.6 AEP: existe, mas não é roundtrip geral sem perdas

A revisão inspecionada **já implementa import/export AEP**, contrariando README/gaps antigos. Fonte e relatórios específicos novos prevalecem. Parser RIFX e roundtrip estrutural/byte-identidade de container não demonstram importação semântica nem equivalência visual.

Comandos engine oferecem dryRun/allowLosses; perdas reconhecidas são recusadas por padrão e importação trabalha em estado candidato antes de commit. Porém há limitações permanentes separadas, algumas não contadas como perdas: frame blending, material 3D, níveis de áudio/guides, detalhes de máscara e texto. **Loss count zero não basta.**

ImportOptions baixo nível presume fontes existentes se não receber resolvedor; o wrapper engine fornece resolução concreta, mas falta de fonte/fallback precisa de veto Astra. Majors testados declarados 24–26 incluem AE 25, sem provar compatibilidade de nossos AEPs 25.5.

Export não preserva comentários de camadas, além de várias opções e render queue. Isso atinge UUIDs Astra. Manter original/sidecar, converter em ramo novo, aceitar só subset explicitamente testado. Não prometer ida/volta AE ↔ EC geral; legado incompatível permanece AE.

### 3.7 Maturidade e testes

Upstream se apresenta alpha e não recomenda uso em trabalho de cliente em produção. Há testes de curvas, pixels, CPU/GPU, comandos, encode/decode e fixtures AEP. Documentação recente traz comparações AE de curvas escalares/espaciais, texto e Trim Paths: avanços reais, sem provar paridade do filme Astra. Percentuais antigos de “cobertura” não foram usados como métricas atuais.

Corpus AEP externo ausente pode resultar em skip sem falha. Na PoC configurar `EFFECTCRAFT_AEP_FIXTURES_REQUIRED=1`, registrar casos executados e não contar GPU indisponível como aprovada. CI usa ações compartilhadas em branch mutável: revisar supply chain antes de adotar builds. Nenhuma suíte upstream foi executada nesta análise.

## 4. Matriz funcional

“Totalmente atendido” abaixo aplica-se ao requisito estrutural estreito demonstrado, não à qualidade geral. “Necessita validação prática” significa que há código, mas falta comprovar execução/fidelidade; “Parcialmente” exige adapter/política ou tem perdas; “Não atendido” pode ser responsabilidade Astra ou algo não requerido. O CSV inclui fontes específicas por linha.

| Requisito | Escopo | Classificação | Evidência/limite | Solução |
|---|---|---|---|---|
| Execução headless | Atual | Necessita validação prática | CLI run/render e host Session sem janela; CLI depende de ui-egui na compilação | Compilar worker sem UI e executar em Windows sem AE |
| API Python direta dos crates | Integração | Não atendido | Não foi encontrada binding Python nem ABI C estável para o core | Worker Rust local por stdio; evitar FFI prematura |
| MCP local e respostas compactas | Atual 9.1 | Parcialmente atendido | EC tem MCP; não implementa os contratos/evidências particulares do Astra | Manter facade Astra e suas 55 ferramentas; não expor comandos genéricos |
| Transporte de evidência e quarentena | Atual 9.2 | Parcialmente atendido | Protocolo nativo AE não é contrato EC | Preservar UUID/hash/limites/pendências; novo transporte versionado interno |
| Projeto próprio serializável | Integração | Totalmente atendido | Project serializável em ecproj/ecprojx existe; isso não é um formato neutro Astra | IR Astra versionado e adaptador; cache ecproj derivado |
| Importação geral AEP sem perdas | Legado | Parcialmente atendido | Importador real com relatórios, allowLosses e limitações permanentes | Cópias; preflight; recusar fora da whitelist; manter AE para legado incompatível |
| Exportação geral AEP e identidade Astra | Legado | Parcialmente atendido | Exportador real não preserva comentários de camadas e outras opções | Não prometer roundtrip; preservar AEP original e mapa UUID independente |
| UUID persistente e proteção de não alvos | Atual | Parcialmente atendido | IDs EC numéricos não substituem sidecar e verificação Astra | UUID canônico; mapas por backend; comparar todo estado não alvo |
| Composições e camadas 2D | Atual 6 | Necessita validação prática | Modelo Comp/Layer e renderizador implementados | Testar hierarquias, bounds e imagens do subconjunto atual |
| Nulls, parenting e preserve-world | Atual 6 | Necessita validação prática | Parenting e transformações existem; semântica Astra requer conversão | Adaptar matrizes e validar estados antes/depois |
| Pré-composições, ciclos e dependências | Atual 6 | Parcialmente atendido | Composições aninhadas existem; regras de edição Astra são próprias | Reusar core; manter fechamento de dependências e veto a ciclos |
| Timing, FPS e stretch | Atual 6/8 | Necessita validação prática | Ticks inteiros e FPS racional; keys locais à camada | Converter frames/segundos/ticks/start/stretch com política explícita |
| Transformações e keyframes manuais | Atual 8 | Necessita validação prática | Linear/Hold/Bezier, velocidades e tangentes disponíveis | Normalizar unidades e amostrar trajetórias; proteger flags automáticas |
| Edição protegida de animações | Atual 8 | Parcialmente atendido | Core oferece comandos de edição; não os guardas de negócio Astra | Manter modos/janelas/boundaries/hash/at-most-once |
| Oito skills de movimento e stagger | Atual | Parcialmente atendido | Planejadores existentes são reutilizáveis; entrega é AE específica | Reusar math/planner; adaptar tracks/máscara e verificar |
| Expressões AE arbitrárias e JSX | Legado protegido | Não atendido | Boa e scripting não equivalem a ExtendScript/AE host | Manter expressões protegidas; não traduzir nem executar JSX arbitrário |
| Textos point/box e estilos por intervalo | Atual 7 | Necessita validação prática | Shaping, parágrafos, StyleRuns e glifos implementados | Converter codepoints, medir bounds e comparar tracking/leading |
| Fonte exata sem substituição silenciosa | Atual 7 | Parcialmente atendido | Resolvedor EC pode usar Inter/fallback de glifo | Preflight face/PostScript e hash de arquivo; bloquear divergências |
| Animadores de texto chars/words | Atual 7 | Necessita validação prática | Seletores/animadores disponíveis; AEP export limita subset | Validar seleção, ordem e bounds; preservar no IR |
| Paths, morph, fills, strokes, Trim Paths | Atual 7 | Necessita validação prática | Operadores nativos e interpolação existem | Casos de winding, paint order e morph compatível obrigatórios |
| Importação SVG estrita | Atual 7 | Parcialmente atendido | EC possui importador; subset/rejeições Astra são mais específicos | Manter parser/allowlist; sem rasterização silenciosa |
| Tokens e layouts responsivos | Atual 7 | Parcialmente atendido | Astra define tokens e algoritmo; métricas vêm do backend | Reusar política; substituir medições; testar três proporções |
| Fill e Gaussian Blur nativos | Atual 9 | Necessita validação prática | ec.generate.fill e ec.blur.gaussian; mapas ADBE reais | Comparar cor/alpha/dimensões/repeatEdge/feather em CPU e GPU |
| Máscaras Add/Subtract e text reveal | Atual | Necessita validação prática | Máscaras e propriedades implementadas; import/export não completo | Validar feather/opacity/inversão e máscaras animadas |
| Mattes alpha/luma e blends atuais | Atual 6 | Necessita validação prática | Mattes e múltiplos blends existentes | Testar todos os quatro blends e inversões com alpha |
| Planos imutáveis, revisão e conflitos | Atual 9 | Parcialmente atendido | Undo/comandos EC não são transação versionada Astra | Manter hashes/dependências; adaptar inspeção e promoção |
| Captura manual e restore do legado | Atual 9 | Parcialmente atendido | AE continua necessário para estado manual nativo incompatível | Preservar ramo AE; restore por tipo de artefato; sem sync automático |
| Render de frames com alpha | Atual/11 | Necessita validação prática | CPU f32 e PNG/TIFF/EXR disponíveis no código | Primeiro comparar PNG sem perdas; validar premultiplicação/cor |
| H.264 final e validação independente | Atual/11 | Necessita validação prática | Exportador nativo e codecs existem; qualidade não medida aqui | Começar PNG → FFmpeg Astra; ffprobe + decode completo |
| GPU Windows e desempenho | Integração | Necessita validação prática | wgpu headless opcional; CPU não desaparece | Benchmark CPU/GPU, p95/RSS/VRAM e fallback explícito |
| Áudio: trim/gain/fades/mix | Futuro 10 | Parcialmente atendido | Mixdown/core de áudio existem; ferramentas Astra faltam | Reusar DSP; implementar APIs tipadas, inspeção e clipping QA |
| Onsets, marcadores e sincronização | Futuro 10 | Parcialmente atendido | Capacidade de áudio não prova workflow planejado | Implementar detector/confiança/edição e erro <=1 frame |
| Final >=30s, alpha/intermediários | Futuro 11 | Parcialmente atendido | Codecs/presets EC ajudam; produção Astra atual não generaliza API | Construir presets, filas, validação e pacote reabrível |
| Pacote com assets e fontes | Futuro 11 | Parcialmente atendido | Formatos e paths não equivalem a pacote Astra verificável | Manifest/hash/roots; licença de fontes; reopen sem links faltantes |
| Director rico e revisão artística | Futuro 12 | Não atendido | Motor não substitui brief/storyboard/semântica nem aprovação humana | Manter e ampliar Director Astra conforme roadmap |
| Fila durável, retomada e cancelamento | Futuro 13 | Parcialmente atendido | Export queue/cancel EC não têm contratos duráveis Astra | Ownership/reconciliação; preservar desconhecidos; isolar outputs |
| Contenção de arquivos e execução | Atual/13 | Parcialmente atendido | Confinement opcional existe, mas comandos genéricos são amplos | Ativar confinamento e permitir só API tipada; dirs privados |
| 3D, câmeras, iluminação | Fora do ciclo atual | Necessita validação prática | Há implementações; sem paridade profissional demonstrada aqui | Avaliar separadamente; não ampliar PoC nem bloquear 2D |
| Plugins de terceiros AE | Não requerido | Não atendido | WASM/efeitos EC não equivalem ao SDK Adobe | Sem impedimento para o Astra atual; bloquear projetos opacos |
| Geração/entendimento semântico por IA | Orquestração | Não atendido | Crates/modelos auxiliares não fornecem o produto de IA Astra completo | Manter Codex/host e Director; não depender de modelo pago novo |


## 5. Alternativas de integração

| Alternativa | Vantagens | Limites/custo | Parecer |
|---|---|---|---|
| A — CLI/subprocesso | Menos código inicial; comandos/render prontos; isolamento; revisão fixa fácil de testar. | Startup/serialização; superfície ampla; dependência de build UI; lock de projeto pode apenas avisar quando aquisição falha, não garante transação Astra. | Melhor instrumento inicial. Cópias privadas e lock estrito Astra. |
| B — crates/biblioteca | Tipos e Session diretos, controle de cache, seleção de build sem GUI. | API interna instável, toolchain/patches; Python exige FFI ou processo; embed compartilha falhas. | Melhor reutilização técnica dentro do worker. |
| C — serviço independente | Isolamento, ownership, limites, cache persistente e workers escaláveis. | IPC, processo, recovery/cancelamento e distribuição próprios; rede adiciona autenticação/multiusuário/paths. | Recomendado como worker local privado stdio usando B. HTTP remoto desnecessário agora. |

A pode preceder B+C. Não criar daemon complexo antes de medir. Não expor MCP genérico EC, execute/script ou ferramentas de shell ao cliente Astra.

Stdout continua protocolo; logs stderr. Handshake de versão/capabilities, UUID/status/deadline, confirmação e arquivo de resultado com tamanho/hash. Dados grandes não viram resposta MCP volumosa. Launcher exit não comprova operação concluída.

## 6. Arquitetura proposta

```text
Host/Codex → ferramentas MCP Astra e respostas compactas
                    │
Astra Python: planos, políticas, projetos, revisão, jobs, evidências
                    │
Astra Scene IR versionado + verificador semântico + EngineAdapter
   ├─ AE adapter → bridge atual → AE/aerender
   └─ EC adapter → IPC local → worker Rust privado
                                └─ engine/host/render/export (+GPU opcional)
Frames/áudio → encoder selecionado → ffprobe/decode → revisão visual
```

É proposta, não código implementado. IR deve conter UUIDs, mídias/fontes e hashes, deps, comp/layer, FPS racional/frames e timing local, tracks/controles explícitos, vetores/texto, IDs semânticos de efeitos, cor/alpha e intenção de export. Campos por backend em namespace/schema próprio. Não tratar ecproj como AEP nem usar hashes antigos como prova de estado convertido.

Fronteira interna mínima: capabilities, inspect, validate, apply operações tipadas, save/reopen, render frames, job status. Recurso não suportado falha antes de mutação; nada de fallback silencioso de engine.

Reusar prioritariamente math/quantização e skills; políticas de revisão/conflitos; compactação/evidence store; parser SVG estrito; parte algorítmica de tokens/layout; snapshots/promoção; FFmpeg/probe. Separar campos AE antes de chamar algo “neutro”. Reusar upstream interpolador, shaping, paths/operadores, filtros, render/cache/mixdown e encoders, sem reconstruir o motor em Python. Regras Astra de fonte, UUID, at-most-once e história não são resolvidas pelo undo EC.

Worker deve ter config/plugins/helpers/modelos/cache privados. Host instala serviços/hooks; não assumir closure mínimo. Habilitar confinement e permitir apenas comandos tipados/paths aprovados, incluindo resolução de symlinks. Desativar scripting/instalações/descoberta externa não necessários.

O Cargo root contém patches, incluindo forks e parsers. Novo workspace de worker não herda automaticamente esses patches. Selecionar/pinar os necessários, gerar lock específico e auditar target/features; não carregar patches GUI por inércia.

## 7. Migração gradual

1. Aprovar EC-0 isolada. Fixtures/cópias; sem tocar na sessão aberta.
2. Congelar referências: AE/fontes/assets/cor/FPS/metadata/keys/frames. Completar revisão humana para declarar uma entrega referência artística.
3. Extrair contratos mínimos/IR e adapter AE preservando comportamento. Schemas novos explícitos, sem reinterpretar histórico.
4. Shadow mode: render EC paralelo, sem promoção/substituição de entregas AE. Guardar comparação e falhas.
5. Novos projetos opt-in com capability aprovada. Não converter tudo nem trocar default.
6. Expandir design/curvas/efeitos por gates; áudio e finalização alinhados ao roadmap.
7. Legado opcional: dry-run AEP em cópia, fontes/limitações/whitelist; alternativa é exportar subset verificado pelo adapter AE para IR. Ambos precisam de diff semântico e visual, não dão migração universal.
8. Só após aceite e autorização, default EC para novos projetos. AE pode continuar necessário para legado sem afetar independência dos novos.

Rollback retorna seleção ao AE e último manifest verificado. Originais, backups, mapas, planos, jobs e evidências permanecem. Versões AE/EC são ramos com proveniência; não sincronização bidirecional automática. Alteração manual posterior em AE exige nova captura/plano, sem sobrepor ramo convertido por suposição.

## 8. Riscos e licenciamento

| Risco | Nível | Mitigação |
|---|---|---|
| Texto/paint order/blur/alpha/cor diferentes | Alto | Referência lossless, ROI por frame, fonte exata e revisão real. |
| AEP com limitações fora de loss count | Alto | Whitelist, relatório completo, diff e manter legado AE. |
| Comentários/IDs perdidos | Alto | UUID canônico independente; preservar original e sidecar. |
| API/schema alpha | Alto | Commit/lock fixos, adapter estreito e upgrade com fixtures. |
| RAM/VRAM/paralelismo | Alto | Limites por job/worker e benchmark RSS/VRAM/backpressure. |
| Crash/timeout/cancelamento | Alto | Job privado e durável, evidência retida, promoção só após verificação. |
| Inputs/plugins/scripts/paths | Alto | Dados tipados, confinamento, diretórios privados, input confiável e allowlist. |
| Distribuição/codecs/licenças | Alto | Closure/SBOM completos, notices/fontes/marcas e revisão comercial. |
| Manutenção de dois engines | Médio/alto | Subset pequeno, testes compartilhados; não abandonar AE cedo. |

### Licenças efetivas verificadas

Raiz é **MIT OR Apache-2.0**, com arquivos LICENSE-MIT, LICENSE-APACHE e NOTICE lidos. Há possibilidade de uso comercial cumprindo obrigações; isso não libera automaticamente marcas, fontes e patentes de terceiros. Concessão Apache é limitada às contribuições pertinentes, não garantia sobre codecs.

Foram verificados 14 arquivos selecionados de manifests/licenças git fixados e **22 versões de pacotes de registry**, baixando archives e confrontando checksum com Cargo.lock. Os manifests e licenças/notices foram preservados. A amostra crítica é permissiva (MIT/Apache/BSD e alternativas); não foi identificado nela um impeditivo à PoC. Isso **não certifica as 746 entradas nem o futuro binário**.

Exemplos: wgpu 30.0.1 MIT/Apache; harfrust 0.12 MIT; tiny-skia 0.11.4/0.12 BSD-3; skrifa 0.44 MIT/Apache; Boa 0.22 Unlicense/MIT; Rayon 1.12 MIT/Apache. FilmCraft fixado em d5ead4ba1ee2f1cd13cb86a4239aee2730a3d9f5 tem licenças raiz permissivas e manifests de codecs herdando workspace.

Fontes bundled Inter/Noto Serif/JetBrains Mono usam OFL; closure GUI pode trazer outras fontes/licenças. Fonte comercial instalada não está automaticamente licenciada para redistribuição. Não copiá-la para pacote por padrão. Documento de marca ArtCraft impõe remover/substituir marcas/logos em distribuição derivada modificada; preservar notices legítimos e não sugerir endosso.

**Antes de incorporar/distribuir:** SBOM do target/features exatos, licenças transitivas/notices/fontes completos, advisories e avaliação de implicações comerciais dos codecs. Não se afirma ausência de GPL em todo o grafo nem ausência de patentes. Esta não é liberação jurídica do produto; a auditoria completa é gate, antes da integração definitiva.

## 9. Sprint proposta EC-0 — validação

Objetivo: demonstrar subset 2D Astra sem AE, preservando integridade e medindo qualidade. Começa só após aprovação. Estimativa inicial de investigação: uma sprint de 1–2 semanas de engenharia, dependente de build/fixtures/licenças; não promessa de migração nesse prazo.

### Entregas

1. Fixar commit/toolchain/lock e ambiente Windows x64; comprovar grafo mínimo sem GUI. Não apagar UI upstream.
2. Testar CLI em fixtures isoladas; worker mínimo cobre o mesmo recorte, não plataforma genérica.
3. Rota experimental Astra com feature flag: comandos tipados, IDs, save/reopen, inspeção e render; default preservado.
4. Comparação CPU primeiro; GPU e encoder nativo em provas separadas. PNGs/metadata/métricas/logs/falhas retidos.
5. Após mudanças funcionais, executar a regressão exigida `.\.venv\Scripts\python.exe -m pytest -q`. Testes AE reais separados/sequenciais, habilitados conscientemente e preservando o projeto aberto/pendências.
6. Auditar closure mínimo antes de recomendar incorporação; fechar gates com resultado e restrições.

### Fixtures

- F1: 5 s/960×540/24 fps, point/box text, AÇÃO, acentos combinados/caracteres relevantes, ranges/animadores; fontes fixas e caso negativo missing font.
- F2: Linear/Hold/Bezier temporal/espacial, overshoot/boundaries, modos de edição, conflito manual, start/stretch e não alvos intactos.
- F3: três precomps, null/parenting preserve-world, mattes/blends, morph/Trim e SVG com paint order conhecido.
- F4: Fill/Blur dimensions/repeatEdge, máscaras/inversão/feather/opacity, transparência/cor/premultiply; shutter se usado na referência.
- F5: save/reopen, UUID, restore como nova versão, original intacto; AEP dry-run com perda conhecida, limitação permanente e fonte ausente; recusa antes de commit.
- F6 separado: áudio 20 s/dois SFX e sync, sem declarar Sprint 10 concluída.
- F7: stress 3/40/80 camadas, três níveis de nesting, 1080p30/30 s; depois cópia da entrega 55 camadas/112 motions.

### Aceite proposto, congelado antes de executar

| Dimensão | Gate |
|---|---|
| Headless | Render EC sem AE/janela; worker sem egui/eframe/winit/UI no grafo efetivo, ou residual identificado e resolvido antes de adoção. |
| Estado | IDs únicos, zero ciclos/links faltantes, hashes originais intactos; reopen e não alvos equivalentes; conflito/capability ausente recusa antes de escrita. |
| Curvas/tempo | Frames/timestamps exatos conforme política; erro escalar absoluto/relativo 1e-5 e espacial <=0,1 px no subset. |
| Visual | PNG com fonte/cor idênticas; por ROI/frame SSIM >=0,99 e MAE <=2/255; bounds texto <=1 px. Inspecionar outliers/edges: fundo vazio não pode ocultar objeto errado. |
| Alpha | Casos lossless equivalentes com erro <=1/255; diagnosticar divergência, sem relaxar após falha automaticamente. |
| Revisão | Sem objeto ausente/ordem errada/fonte substituída/clipping/texto ilegível. Frames vistos registrados; playback/arte separados. |
| Vídeo/áudio | Frames exatos, FPS/dimensões corretos, duração até um frame de diferença e decode completo; áudio quando presente sync <=1 frame e sem clipping. |
| Protocolo | UUID/status/tamanho/SHA/JSON verificados e compactação mantida; crash/timeout não promove/reenvia e retém pendências. |
| Determinismo | Três renders CPU iguais no mesmo ambiente fixado; comparar 1 vs múltiplas threads. GPU avaliada separadamente, sem exigir hash CPU=GPU. |
| Desempenho | >=5 cold e >=10 warm; mediana/p95, RSS/VRAM e motor/encode/end-to-end separados; mesmo conteúdo/encoder AE/EC. Gate proposto p95 <=1,25× AE; aceleração >=1,5× é meta, não evidência. |
| Recursos | Orçamento pré-fixado: proposta <=4 GiB RSS/worker no stress1080p, reduzida conforme RAM disponível; VRAM limitada ao hardware. Não aumentar limite depois de falhar sem revisão. |
| Jurídico | Closure auditado e notices/fontes/marcas tratados; build bem-sucedido não é liberação comercial. |

Esses números são critérios propostos, não medições ou garantias. Se rasterização legítima impedir um gate, diagnosticar e submeter mudança de requisito explícita antes de promoção. Não contar testes ignorados como aprovados.

Decisões: prosseguir experimentalmente se gates essenciais/subset passarem; prosseguir restrito apenas com capabilities recusando os casos não cobertos; adiar se integridade, visual crítico, estabilidade, headless ou manutenção falharem. Preservar todos os resultados, sem desfazer o backend funcional.

## 10. Impacto no roadmap — proposta

| Etapa | Preservar | Simplificação possível | Trabalho restante/novo |
|---|---|---|---|
| Sprints iniciais/bridge | Aceites e adapter AE | Novos projetos EC dispensam bootstrap/-r/aerender | IPC, processo/ownership e inspeção EC; bridge fica para legado. |
| 6 — cenas | Dependências/cycles/UUID/timing/não alvos | Core comp/layer/precomp/parent/mattes | Adapter e verificação semântica/roundtrip. |
| 7 — design | Fonte/ranges/SVG/tokens/safe areas | Shaping/path/operators core | Métricas/fontes e regressão visual. |
| 8 — animação | Guardas/modes/windows/boundaries | Interpolador/tracks core | Unidades/tempo/flags e comparação AE. |
| 9 — revisão | Imutabilidade/conflito/at-most-once/restore | Comandos e estado EC ajudam | Persistência multiartefato/proveniência e verificação. |
| 9.1 — compactação | Contrato host/queries | Evita repetição da cena inteira | Evidência EC paginável/filtrável. |
| 9.2 — transporte | Protocolo/quarentena AE | EC não sofre limite ACK host AE | Novo contrato interno com mesmos princípios de hash/ownership. |
| 10 — áudio | Inspeção/trim/gain/fades/onsets/confiança/markers/sync | Mixer/DSP upstream | APIs Astra, guards, análise e QA continuam. |
| 11 — finalização | >=30 s/presets/assets/pacote reabrível | Codecs/alpha/intermediários | Contrato ecproj/IR vs AEP exige aprovação; manifest/fontes/paths/decode. |
| 12 — Director | Brief/storyboard/layout/legibilidade/limites | Iterações podem baratear se render mais rápido | Semântica, ritmo e revisão artística não vêm do motor. |
| 13 — robustez | Fila/reconcile/diagnóstico/retenção | Worker ajuda isolamento/cancel | Recovery, locks estritos, retenção e upgrades fixados. |

Inserir EC-0 antes de reescrita ampla. Depois, condicionalmente: EC-1 contratos/adapter mínimo; EC-2 paridade subset6–9; EC-3 áudio/finalização alinhados a10–11; EC-4 hardening/upgrades alinhados a13. Parte da robustez é requisito já na EC-0, não deve esperar EC-4. São pacotes para decisão futura, não autorização concedida.

Áudio/intermediários/efeitos podem ser experimentados antecipadamente sem reconstruir DSP. Não eliminar Sprints10–13: primitivo Rust não entrega automaticamente API segura, persistência, workflow ou arte. 3D/câmeras/partículas continuam fora do ciclo até decisão própria.

## 11. Fontes e evidências

Links abaixo usam a revisão exata; documentos antigos podem divergir do código novo, como ocorreu com AEP.

- [README.md](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/README.md)
- [Cargo.toml](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/Cargo.toml)
- [Cargo.lock](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/Cargo.lock)
- [apps/effectcraft-cli/Cargo.toml](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/apps/effectcraft-cli/Cargo.toml)
- [apps/effectcraft-cli/src/main.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/apps/effectcraft-cli/src/main.rs)
- [crates/host/src/lib.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/host/src/lib.rs)
- [crates/engine/src/services.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/engine/src/services.rs)
- [crates/project/src/lib.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/project/src/lib.rs)
- [crates/time/src/lib.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/time/src/lib.rs)
- [crates/keyframe/src/lib.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/keyframe/src/lib.rs)
- [crates/text/src/fonts.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/text/src/fonts.rs)
- [crates/effects/src/color_fx.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/effects/src/color_fx.rs)
- [crates/effects/src/misc.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/effects/src/misc.rs)
- [crates/render/src/lib.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/render/src/lib.rs)
- [crates/render/src/cache.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/render/src/cache.rs)
- [crates/export/src/lib.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/export/src/lib.rs)
- [crates/aep/src/import/report.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/aep/src/import/report.rs)
- [crates/aep/src/export/report.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/aep/src/export/report.rs)
- [crates/engine/src/cmd/aep.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/engine/src/cmd/aep.rs)
- [crates/automation/src/confine.rs](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/crates/automation/src/confine.rs)
- [LICENSE-MIT](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/LICENSE-MIT)
- [LICENSE-APACHE](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/LICENSE-APACHE)
- [NOTICE](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/NOTICE)
- [docs/brand/LICENSE-brand.txt](https://github.com/storytold/effectcraft/blob/a41ff5015c6687db15a6f074a47b870b8f09fece/docs/brand/LICENSE-brand.txt)

Evidências locais: astra-inventory.json (módulos/rotas/hashes); effectcraft-inventory.json (manifests/dependências); dependency-evidence/manifest.json (git); dependency-evidence/registry/audit.json (22 versões registry); matriz-compatibilidade.csv (40 requisitos/fontes/soluções); integrity-review.json (conferência final dos fingerprints e entregáveis).

Referências Astra: README.md, AGENTS.md, ASTRA_VIDEO_STUDIO_PRO_ROADMAP.md, docs/decisions.md, test-report.md, compact-responses.md, native-result-transport.md, scene-editing.md, design-tools.md, animation-editor.md e revisions.md. Inventário registra hashes observados, não certifica toda alegação histórica.

## 12. Decisão solicitada

**Aprovar apenas EC-0, a validação isolada da seção9.** Ela produzirá resultado comparativo e proposta de implementação revisada. Não autoriza retirar AE, converter sessão atual, distribuir codecs/fontes, trocar default ou migrar todos os projetos.

É viável investigar um Astra independente de AE reutilizando esse motor. A substituição com qualidade preservada ainda precisa ser demonstrada. O próximo investimento deve produzir essa evidência com reversibilidade.
