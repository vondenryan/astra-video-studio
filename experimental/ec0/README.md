# EC-0 — prova de conceito isolada

Primeiro marco experimental do Astra Studio com o núcleo de render CPU do EffectCraft. **Não é o adapter EC-1, não adiciona ferramentas MCP e não troca o backend After Effects.** A fixture é fixa: composição de160×90,30fps, seis frames e dois sólidos opacos originais. Não recebe JSX, scripts, cenas arbitrárias, mídia ou comandos do host upstream.

O segundo marco acrescenta outro binário privado, `astra-ec0-text-curves`, com casos fixos de texto e curvas. O primeiro binário, plano e relatórios permanecem preservados.

O terceiro marco acrescenta `astra-ec0-compositing` com casos fixos de Fill, Gaussian Blur, paths nativos, Trim Paths, morph, máscaras, mattes e precomps com parentesco.

## Referências fixadas

- EffectCraft: `a41ff5015c6687db15a6f074a47b870b8f09fece`.
- Rust: `1.95.0`, target `x86_64-pc-windows-msvc`.
- Rustup: `1.28.2`, instalador oficial verificado por SHA-256.
- Dependências exatas: `worker/Cargo.lock`, separado do lock de todo o upstream.
- Gates: [acceptance-plan.json](acceptance-plan.json), copiado e fixado por hash em cada ensaio. Os gates completos da EC-0 continuam válidos.

Os crates são referenciados diretamente pelo Git/revisão upstream. Não há cópia/modificação do checkout upstream nem dependência dos frontends CLI/GUI. A compilação usa o linker/SDK MSVC já instalado e duas tarefas. Rust, Cargo, dependências e saídas ficam no workspace; o instalador não altera o PATH global. Não são distribuídos binários, fontes ou plugins.

## Executar explicitamente no PowerShell

Instale antes o ambiente Python do Astra e as ferramentas de C++/SDK do Visual Studio. A preparação pode baixar o Rust privado e as dependências; requer rede e espaço em disco.

```powershell
.\experimental\ec0\prepare.ps1 -Action metadata
.\experimental\ec0\prepare.ps1 -Action build
.\experimental\ec0\prepare.ps1 -Action test
.\.venv\Scripts\python.exe experimental/ec0/run_smoke.py
```

Para a fixture de texto/curvas, após preparar metadata/build/test:

```powershell
.\.venv\Scripts\python.exe experimental/ec0/run_text_curves.py
```

Para testar a composição com a mesma preparação de metadata e build, execute:

```powershell
.\.venv\Scripts\python.exe experimental/ec0/run_compositing.py
```

O controlador compara amostras RGBA dos PNGs decodificados, verifica a reabertura do projeto e compara os hashes das imagens em três execuções. As recusas de dependências e os resultados completos ficam no diretório indicado por `workspace/ec0/compositing-current.json`.

Os modos adicionais exercitam a importação pelo parser SVG do Astra e a animação de opacidade por um seletor de caracteres. Use o mesmo build.

```powershell
.\.venv\Scripts\python.exe experimental/ec0/run_compositing.py --svg
.\.venv\Scripts\python.exe experimental/ec0/run_compositing.py --text-selector
```

O modo SVG guarda o input, os paths lidos após reabrir, o projeto editado e o diff de pixels. O modo de texto usa JetBrainsMono-Regular fixada no plano e confere a revelação nos frames 0, 15 e 30. Os ponteiros para as evidências são `workspace/ec0/svg-current.json` e `workspace/ec0/text-selector-current.json`. [Relatório](../../docs/effectcraft/ec0-svg-selector-milestone.json)

Ela usa Inter-Regular dos bytes embutidos no upstream, verificados por SHA, sem varrer fontes do sistema. Recusa fonte ausente, hash incorreto e caractere sem cobertura antes de criar o slot. Verifica texto point/box, uma faixa de cor por pontos de código, 61frames640×360/30fps, curvas Linear/Hold/Bezier e trajetória espacial manual com passagem intermediária não parada. Amostras são comparadas a referências independentes em Python; três execuções1/2/1 threads devem produzir PNGs idênticos. A checagem de bounds confronta geometria e raster EC, sem alegar paridade com AE. Animadores de texto continuam pendentes.

`text-curves-plan.json` fixa os critérios; `text-curves-layout-amendment-01.json` registra o ajuste explícito de baseline da caixa após um preflight reprovado, sem relaxar overflow ou tolerâncias. `font-assets-manifest.json` inventaria os sete arquivos OFL embutidos pelo crate de texto. Os fontes não são copiados para este repositório; o executável local usa os bytes do checkout fixado. Isso não fecha a auditoria de todas as dependências/notices.

Cada execução nova usa `workspace/ec0/text-curves-<UUID>` e jobs novos em `workspace/ec0/text-curves-runs/<UUID>`. O ponteiro `text-curves-current.json` referencia a verificação por hash. Recusas conhecidas são verificadas por identidade/status/ausência de outputs antes de arquivar seus marcadores; erro inesperado ou timeout fica pendente, sem kill/replay. A confirmação e os arrays completos ficam em arquivos locais; stdout contém apenas receipt limitado.

O ensaio salva e reabre `.ecproj`, recusa reparações inesperadas, verifica pixels de referência e publica PNGs. Repete com1/2/1 threads, compara hashes dos frames e usa FFmpeg/FFprobe para encode/contagem/decode completo. Verifica hashes dos AEPs preexistentes em `workspace/projects`, sem executar comandos no AE. O processo roda sem janela pelo controlador.

Cada job usa uma pasta nova, exclusiva, sob `workspace/ec0/runs/<UUID>`. Plano, stdout/stderr, exit code e verificação ficam em `workspace/ec0/smoke-<UUID>`. Slots existentes não são sobrescritos. O controlador grava intenção antes de executar e mantém `pending.json` em erro/timeout; não mata/reenvia o worker. Uma pendência deve ser inspecionada antes de outro ensaio, sem apagar evidência para forçar continuação. Isso é um harness experimental, não o sistema de recuperação/filas de produção.

O inventário `dependency-closure.json` descreve o grafo efetivamente alcançável para Windows. Ele verifica nomes de frontends conhecidos e registra licenças declaradas/features; não é auditoria integral dos textos de licença, SBOM legal completo ou liberação de distribuição. O worker mantém a identificação upstream e não incorpora sua marca/arte.

## O que falta para fechar EC-0

O quinto marco comparou um gráfico estático e uma curva escalar com evidência arquivada do AE. Também executou um dry run em 17 AEP/AEPX do corpus fixado. Restam a suíte upstream com corpus obrigatório, a ampliação da paridade visual e da cobertura de fontes e animadores, as medições de desempenho e memória e a auditoria de licenças e notices. GPU e encoders nativos têm validação própria.

Para reproduzir a comparação no workspace que contém a referência da Sprint 11, mantenha o corpus fixado em `workspace/ec0/corpus-97262276`, atualize o inventário e compile com `prepare.ps1 -Action metadata` e `prepare.ps1 -Action build`. Execute `.\.venv\Scripts\python.exe experimental/ec0/run_parity.py` na raiz do repositório. Cada tentativa guarda cópias dos insumos verificados, o inventário, os relatórios e os hashes em `workspace/ec0/parity-<UUID>`. O controlador trabalha com arquivos arquivados e não se conecta ao AE.

Estado e evidências: [andamento da EC-0](../../docs/effectcraft/ec0-progress.md). A EC-1 continua condicionada ao relatório gate a gate e a uma decisão específica.
