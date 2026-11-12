# EC-0 — andamento e primeiro marco

Data:10/11/2026. A nova orientação do operador retoma a trilha anteriormente adiada. **EC-0 em andamento; não encerrada.** EC-1–4 continuam condicionadas aos gates e a decisões específicas.

## Escopo executado — primeiro marco

- Rust1.95.0/x64 MSVC instalado em `workspace/ec0`, sem alterar o PATH global. Instalador Rustup1.28.2 oficial com SHA-256 verificado; SDK/linker MSVC já existentes no computador.
- Worker próprio mínimo, com crates do EffectCraft fixados em `a41ff5015c6687db15a6f074a47b870b8f09fece`. Lockfile próprio versionado. Nenhum fork ou alteração do upstream.
- Grafo resolvido para Windows:87 pacotes alcançáveis, sem os frontends GUI identificados. Usa os crates de projeto/render CPU diretamente, sem CLI, engine/host de comandos gerais ou UI upstream.
- Fixture fixa de160×90/30fps/seis frames: dois sólidos opacos originais. Persistência `.ecproj` e reabertura semanticamente iguais, sem reparações; pixels de referência e ordem das camadas verificados.
- Três execuções CPU com1/2/1 threads produziram PNGs byte-idênticos. Slot concluído e IDs de job inválidos foram recusados sem modificar o job anterior.
- Sequência codificada com FFmpeg em H.264/yuv420p; FFprobe confirmou dimensões,30fps/seis frames/0,2s; decode completo passou.
- 2.439 AEPs/snapshots existentes em `workspace/projects` mantiveram seus hashes. Nenhum comando foi enviado ao AE; não foi necessário fechar ou reiniciar a aplicação.

O build inicial do recorte levou1m33s em perfil dev, sem representar benchmark de render. Os tempos do harness incluem startup/persistência/PNG e não são mediana/p95 ou comparação AE/EC. O inventário de licenças declaradas não substitui a auditoria de textos, notices, fontes, codecs ou distribuição.

## Gates

| Gate | Estado atual |
| --- | --- |
| Build Windows fixado e recorte sem frontend GUI | Verificado no worker CPU mínimo. |
| Persistência/reabertura | Verificada nas fixtures de sólidos, texto, curvas, composição, SVG e seletor de caracteres. Revisões gerais pendentes. |
| Render headless e encode/decode independente | PNGs verificados nas fixtures e H.264 com decode completo nos marcos de sólidos e texto/curvas. |
| Determinismo CPU | Séries de três execuções com 1/2/1 threads verificadas nas fixtures dos quatro primeiros marcos. |
| Fontes/texto/missing-font | Inter-Regular e JetBrainsMono-Regular fixadas por hash, texto point/box, faixa de cor e seletor de caracteres verificados. Fontes arbitrárias e paridade tipográfica com AE pendentes. |
| Curvas, tangentes, boundaries e semântica de tempo | Fixtures manuais e comparação de uma curva escalar com inspeção AE verificadas. Edição e retiming gerais pendentes. |
| Fill/Blur, vetores, máscaras/mattes e dependências | Terceiro e quarto marcos verificaram as fixtures CPU. Comparação visual equivalente com AE pendente. |
| Identidade Astra/IR/revisões/conflicts | Pendente; IDs internos EC não foram apresentados como IDs AE. |
| AEP dry-run/corpus e limitações permanentes | Quinto marco analisou 17 projetos do corpus fixado e verificou as recusas com perdas. Ver o sexto marco para a suíte upstream. |
| Comparação visual/semântica com AE | Gráfico estático e curva escalar verificados no quinto marco. Texto e cenas animadas pendentes. |
| Stress1080p, memória,5cold/10warm e p95 | Pendente. |
| Closure de licenças/notices/SBOM | Inventário de manifests/features disponível; auditoria completa pendente. |
| GPU e encoder nativo | Não executados; têm gates separados. |
| Integração MCP/adapter de produção | Não implementada;77 ferramentas atuais inalteradas. |

Os limites do roadmap estão fixados em `experimental/ec0/acceptance-plan.json`, copiado/hash-verificado em cada ensaio. Nenhuma tolerância foi relaxada. O primeiro marco não converte os demais gates em aprovados nem autoriza mudança de backend.

## Evidências e reprodução

[Instruções de execução](../../experimental/ec0/README.md), [worker](../../experimental/ec0/worker/src/main.rs) e [harness](../../experimental/ec0/run_smoke.py).

`workspace/ec0/smoke-current.json` aponta o último ensaio e seu SHA de verificação. Cada pasta `smoke-<UUID>` retém plano, metadados/grafo fixados por hash, baseline AEP, stdout/stderr/exit, snapshots dos marcadores e verificação com hashes de todos os outputs. Jobs e projetos sintéticos ficam em `workspace/ec0/runs/<UUID>`. Metadados de dependências usam diretórios novos sob `workspace/ec0/evidence/metadata-<UUID>`; o ponteiro atual não substitui registros anteriores.

Em timeout/erro do worker, o marcador de intenção/execução permanece. O harness recusa novos ensaios enquanto houver pendência; não mata nem reenvia o processo. Isso não implementa ainda a recuperação/ownership completa do adapter de produção.

## Segundo marco — texto e curvas manuais

O worker adicional valida Inter-Regular por identidade PostScript e SHA-256 dos bytes embutidos no upstream. Não usa descoberta de fontes do sistema, síntese de estilo nem fallback por glifo. Fonte inexistente, hash incorreto e caractere sem cobertura foram recusados antes de criar arquivos de saída. Isso é um recorte fixo, não um resolvedor geral de fontes instaladas.

A fixture640×360/30fps tem61frames, texto point/box e uma faixa de cor nos quatro primeiros pontos de código de “AÇÃO”. O mapeamento UTF-8 é explícito e a persistência/reabertura preserva texto, estilos, propriedades e chaves sem reparações. O primeiro preflight de caixa falhou com ink0,563156px acima da caixa; o ajuste de baseline-2px foi registrado em amendment separado. Os logs falhos e o plano inicial foram preservados; não houve relaxamento de overflow.

Linear/Hold/Bezier escalar foram comparados a formas fechadas; o caminho espacial usa um oráculo independente por comprimento de arco, não uma reimplementação usada para renderizar. Foram verificadas63amostras, incluindo antes/depois do intervalo,9casos de start/stretch e16conversões frame/tick. A passagem intermediária tem controle de velocidade180px/s; sondas finitas dos dois lados foram compatíveis dentro do limite0,2px/s. Isso não promete continuidade automática para outros tracks.

Resultados medidos: erro escalar máximo2,85e-14; erro espacial máximo2,70e-7px; erro de velocidade da passagem0,03575px/s; diferença entre as duas sondas0,00433px/s. Bounds de texto confrontados com pixels do raster EC ficaram em1px, limite fixado antes dos testes. Essa comparação interna não fecha o gate de bounds/paridade com AE.

Três execuções1/2/1 threads produziram sequências PNG idênticas; o movimento gerou frames distintos ao longo do tempo. H.264,61frames/30fps e decode completo passaram.2.439 AEPs/snapshots conservaram hashes, sem comandos ao AE. O grafo atual tem95pacotes alcançáveis e nenhum frontend GUI identificado; o inventário histórico de87pacotes do primeiro marco permanece preservado. Os sete assets de fonte OFL do crate são inventariados sem redistribuir arquivos de fonte; auditoria completa de dependências/notices continua pendente.

Três frames da primeira execução bem-sucedida foram extraídos do MP4 correspondente e realmente vistos: texto legível, sem clipping/colisão aparente nessas amostras, e posições do elemento móvel distintas. Não houve playback completo, audição ou aprovação artística humana.

`workspace/ec0/text-curves-current.json` aponta o ensaio final. Seu diretório contém o plano/amendment, grafo/metadata fixados, baseline AEP, stdout/stderr/exits, métricas/oráculos, hashes e outputs; a primeira execução e seus frames vistos continuam preservados. Relatórios compactos versionados: `ec0-text-curves-milestone.json` e `ec0-text-curves-dependency-inventory.json`.

## Terceiro marco — efeitos e composição

Os testes CPU verificaram Fill, o halo e a simetria do Gaussian Blur, a ordem de pintura entre duas camadas vetoriais, Trim Paths e a interpolação de um path com topologia compatível. Também verificaram uma máscara Add com abertura Subtract, mattes alfa e luminância, e uma camada 2D ligada a um null dentro de uma precomp. Os testes de luminância usaram mattes preto e branco para confirmar supressão e revelação.

O projeto reabriu com estado idêntico. Três execuções com 1, 2 e 1 threads produziram os mesmos 12 PNGs. O validador do experimento recusou três referências ausentes e quatro ciclos envolvendo parentesco, matte ou precomp. Os 2.439 AEPs e snapshots conservaram seus hashes.

Os projetos e PNGs de cada job ficam em `workspace/ec0/compositing-runs`. O escopo vetorial deste marco começa em paths nativos. [Plano](../../experimental/ec0/compositing-plan.json) · [Medições e hashes](ec0-compositing-milestone.json)

## Quarto marco — importação SVG e animador de texto

A prova SVG reutiliza o parser estrito do Astra e envia a geometria normalizada ao EffectCraft. O arquivo de teste usa viewBox deslocado, preenchimento herdado, um traço com segmentos quadrático e cúbico e um retângulo sobreposto com 50% de opacidade. A leitura após reabrir conferiu os três paths, tangentes, cores, opacidades, largura, cap e join. Gradientes, transforms e imagens externas foram recusados pelo parser neste recorte.

O worker alterou somente a cor do preenchimento superior e salvou uma versão separada. A leitura do projeto comprovou a preservação das demais propriedades. As amostras RGBA confirmaram composição e transparência, e o diff completo marcou exatamente os 4.032 pixels do retângulo.

A prova do animador usa JetBrainsMono-Regular fixada por PostScript e SHA-256. Um seletor nativo animou o fim do intervalo de caracteres e usou opacidade zero dentro da seleção. Os frames 0, 15 e 30 mostraram zero, um e dois caracteres respectivamente. O canal alfa do segundo caractere coincidiu exatamente nos frames 15 e 30.

Cada prova repetiu a reabertura e o render com 1, 2 e 1 threads. Os hashes dos PNGs e dos projetos coincidiram em cada série. As evidências estão no workspace e os relatórios versionados registram os hashes e os pixels medidos. [Relatório SVG e seletor](ec0-svg-selector-milestone.json)

## Quinto marco — referência do After Effects e corpus AEP

O ensaio conferiu o hash do AEP salvo, do resultado de inspeção confirmado pelo AE e do manifesto da sequência TIFF. A comparação usou os frames 72, 75 e 77 já renderizados no AE 25.5. O EffectCraft importou uma cópia do mesmo AEP em memória e renderizou o elemento gráfico com os mesmos bytes PNG. O título ficou desativado apenas na cópia do EffectCraft porque o arquivo da fonte original não acompanha a referência.

As regiões interna e de borda passaram nos três frames. Todas tiveram SSIM 1, erro RGB médio 0 e erro alfa máximo 0. O ensaio também comparou posição, âncora, escala e opacidade do gráfico, seis keyframes de opacidade do título com interpolação e controles Bezier, e cinco amostras da curva. A propriedade de opacidade é escalar e a comparação de flags cobre os controles temporais aplicáveis.

O dry run verificou os 20 hashes do corpus fixado e analisou os 17 AEP/AEPX sem resolver mídia ou fontes externas. Em modo estrito, 15 importaram em memória. Dois foram recusados, e a recusa preservou o projeto temporário. `effects.aep` registrou cinco perdas em efeitos ou parâmetros e `text.aep` registrou quatro perdas em recursos tipográficos. Fontes e mídias indisponíveis pelo desenho do ensaio aparecem separadamente. Os três arquivos FFX tiveram apenas verificação de hash.

Continuam pendentes a suíte upstream com corpus obrigatório, a paridade visual de texto, efeitos e cenas animadas, as medições de desempenho e memória e a auditoria completa de licenças e notices. [Plano e tolerâncias](../../experimental/ec0/parity-plan.json) · [Medições e hashes](ec0-parity-milestone.json)

## Sexto marco — suíte upstream AEP com corpus obrigatório

O controlador extraiu diretamente do commit fixado os 101 arquivos dos testes e fixtures do crate AEP. Executou o alvo de integração completo, com as dependências e o lockfile do probe isolado, `EFFECTCRAFT_AEP_FIXTURES_REQUIRED=1` e os 20 arquivos do corpus verificados por SHA-256. Os fontes e insumos conservaram os hashes após a execução.

O alvo de integração upstream teve 602 testes aprovados, zero falhas e cinco ignorados, cobrindo leitura, importação, exportação e resistência a bytes corrompidos. Nenhuma fixture obrigatória foi pulada. Os cinco ignorados são dois exploratórios de pares AEP/AEPX, dois de famílias de versões e um de Cryptomatte cuja fixture ainda não está fixada nesse corpus. Os testes unitários da biblioteca e os exemplos são alvos distintos e seguem pendentes.

O primeiro processamento do resultado esperava quatro ignorados e reteve a pendência. A inspeção identificou o quinto caso no fonte fixado, conferiu novamente stdout, saída do processo, fontes, corpus e os 2.498 hashes de AEPs preexistentes. O controlador foi corrigido para conferir a identidade dos cinco casos. A execução concluída foi finalizada por auditoria dos arquivos retidos, com registro próprio e sem reenvio da suíte.

Este marco cobre o alvo de integração hospedado pelo probe. A paridade visual de texto, efeitos e cenas animadas, os benchmarks e a auditoria de licenças continuam pendentes. [Relatório da suíte](ec0-aep-suite-milestone.json)
