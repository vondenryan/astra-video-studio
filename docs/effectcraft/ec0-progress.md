# EC-0 — andamento e primeiro marco

Data:10/11/2026. A nova orientação do operador retoma a trilha anteriormente adiada. **EC-0 em andamento; não encerrada.** EC-1–4 continuam condicionadas aos gates e a decisões específicas.

## Escopo executado

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
| Persistência/reabertura | Verificada apenas na fixture fixa de sólidos; sem edição/revisão geral. |
| Render headless e encode/decode independente | Verificados na fixture estática; o harness inicia o processo sem janela. |
| Determinismo CPU | Três execuções, incluindo1/2 threads, verificadas para a fixture estática. |
| Fontes/texto/missing-font | Pendente. |
| Curvas, tangentes, boundaries e semântica de tempo | Pendente. |
| Fill/Blur, vetores, máscaras/mattes e dependências | Pendente. |
| Identidade Astra/IR/revisões/conflicts | Pendente; IDs internos EC não foram apresentados como IDs AE. |
| AEP dry-run/corpus e limitações permanentes | Pendente. |
| Comparação visual/semântica com AE | Pendente; não há claim de paridade. |
| Stress1080p, memória,5cold/10warm e p95 | Pendente. |
| Closure de licenças/notices/SBOM | Inventário de manifests/features disponível; auditoria completa pendente. |
| GPU e encoder nativo | Não executados; têm gates separados. |
| Integração MCP/adapter de produção | Não implementada;77 ferramentas atuais inalteradas. |

Os limites do roadmap estão fixados em `experimental/ec0/acceptance-plan.json`, copiado/hash-verificado em cada ensaio. Nenhuma tolerância foi relaxada. O primeiro marco não converte os demais gates em aprovados nem autoriza mudança de backend.

## Evidências e reprodução

[Instruções de execução](../../experimental/ec0/README.md), [worker](../../experimental/ec0/worker/src/main.rs) e [harness](../../experimental/ec0/run_smoke.py).

`workspace/ec0/smoke-current.json` aponta o último ensaio e seu SHA de verificação. Cada pasta `smoke-<UUID>` retém plano, metadados/grafo fixados por hash, baseline AEP, stdout/stderr/exit, snapshots dos marcadores e verificação com hashes de todos os outputs. Jobs e projetos sintéticos ficam em `workspace/ec0/runs/<UUID>`. Metadados de dependências usam diretórios novos sob `workspace/ec0/evidence/metadata-<UUID>`; o ponteiro atual não substitui registros anteriores.

Em timeout/erro do worker, o marcador de intenção/execução permanece. O harness recusa novos ensaios enquanto houver pendência; não mata nem reenvia o processo. Isso não implementa ainda a recuperação/ownership completa do adapter de produção.

Próximo recorte: fixtures de fontes exatas/texto e curvas temporais/espaciais, antes de efeitos e comparação AE/EC. A aprovação artística do projeto AE e a aceitação externa Claude9.3 permanecem independentes.
