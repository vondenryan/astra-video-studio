# EC-0 — prova de conceito isolada

Primeiro marco experimental do Astra Studio com o núcleo de render CPU do EffectCraft. **Não é o adapter EC-1, não adiciona ferramentas MCP e não troca o backend After Effects.** A fixture é fixa: composição de160×90,30fps, seis frames e dois sólidos opacos originais. Não recebe JSX, scripts, cenas arbitrárias, mídia ou comandos do host upstream.

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

O ensaio salva e reabre `.ecproj`, recusa reparações inesperadas, verifica pixels de referência e publica PNGs. Repete com1/2/1 threads, compara hashes dos frames e usa FFmpeg/FFprobe para encode/contagem/decode completo. Verifica hashes dos AEPs preexistentes em `workspace/projects`, sem executar comandos no AE. O processo roda sem janela pelo controlador.

Cada job usa uma pasta nova, exclusiva, sob `workspace/ec0/runs/<UUID>`. Plano, stdout/stderr, exit code e verificação ficam em `workspace/ec0/smoke-<UUID>`. Slots existentes não são sobrescritos. O controlador grava intenção antes de executar e mantém `pending.json` em erro/timeout; não mata/reenvia o worker. Uma pendência deve ser inspecionada antes de outro ensaio, sem apagar evidência para forçar continuação. Isso é um harness experimental, não o sistema de recuperação/filas de produção.

O inventário `dependency-closure.json` descreve o grafo efetivamente alcançável para Windows. Ele verifica nomes de frontends conhecidos e registra licenças declaradas/features; não é auditoria integral dos textos de licença, SBOM legal completo ou liberação de distribuição. O worker mantém a identificação upstream e não incorpora sua marca/arte.

## O que falta para fechar EC-0

Fonte exata e missing-font; texto; curvas temporais/espaciais; efeitos; paths/mattes/dependências; dry-run AEP com corpus obrigatório; comparação semântica/visual AE versus EC; benchmarks repetidos e memória; licenças/notices completos. GPU e encoders nativos têm validação separada. Este teste estático de sólidos não aprova essas capacidades, não mede paridade nem qualidade artística.

Estado e evidências: [andamento da EC-0](../../docs/effectcraft/ec0-progress.md). A EC-1 continua condicionada ao relatório gate a gate e a uma decisão específica.
