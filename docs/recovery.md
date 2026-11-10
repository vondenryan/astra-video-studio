# Sprint 13 — persistência, diagnóstico e recuperação

O Astra mantém o MCP local por stdio. Estas ferramentas não recebem comandos, JSX, processos ou caminhos de remoção arbitrários. Reconciliação não é autorização para reenviar trabalho incerto.

## Ferramentas

| Ferramenta | Uso | Efeito |
| --- | --- | --- |
| `queue_inspect` | `scope: active/all`, `offset`, `limit` de até100 | Diagnóstico de fila, processos, disco e bridge; não inicia AE |
| `job_reconcile` | ID e `mode: inspect` | Autentica confirmação tardia, classifica estado e publica evidência; não promove resultados |
| `job_reconcile` | `mode: release_unstarted` e hash do journal inspecionado | Libera exclusivamente uma vaga cujo worker comprovadamente não começou e cujo dono saiu |
| `job_reconcile` | `mode: release_completed` e hash do journal | Libera uma vaga de dono encerrado com resultado já registrado e hashes íntegros, ou cancelamento com saída confirmada; não reprocessa |
| `job_reconcile` | `mode: release_acknowledged_read` e hash do journal | Arquiva e libera apenas a quarentena de uma consulta nativa confirmada, com dono encerrado e bridge ociosa correspondente |
| `project_dependencies` | ID do projeto, `refresh: false/true` | Relatório de mídia/fontes/plugins; leitura nativa explícita quando solicitado |
| `workspace_cleanup_plan` | Até50 IDs, idade mínima24h | Plano imutável com hashes; não apaga arquivos e não há ferramenta de aplicação |

Respostas continuam compactas por padrão. Use `operation_query` sobre o hash de evidência com as seções `jobs`, `diagnostics`, `media`, `fonts`, `issues`, `candidates` e `protected`. Para paginação estável, consulte a evidência da consulta anterior; a lista de jobs atual pode crescer entre chamadas.

## Donos e fila persistente

Jobs novos registram PID, horário de criação do processo e identidade da instância. O horário fornecido pelo sistema operacional distingue um processo original de outro que reutilizou seu PID. Processo existente não prova que o worker responde nem que um comando foi executado no AE. A ausência de identidade em journals antigos é tratada como desconhecida.

A fila tem quatro vagas compartilhadas entre processos do mesmo workspace. Admissão, início e liberação têm registros persistentes. Um lock do sistema operacional protege a admissão; outro serializa o worker de render durante toda a preparação/render/codificação. O mutex global existente continua protegendo as operações da bridge. Os locks desaparecem quando o dono sai, mas isso não conclui o job nem libera automaticamente suas vagas persistentes.

O início do worker é registrado antes de qualquer etapa externa. Uma vaga de worker que nunca começou pode ser liberada explicitamente depois de confirmar a saída do dono, conferir o hash do journal e excluir intenção nativa, lançamento de processo, confirmação ou quarentena correspondente. O journal original permanece intacto; `job_status` apresenta a recuperação como cancelamento sem execução. Para tentar novamente, o operador solicita um job novo — a reconciliação não reutiliza a execução anterior.

Workers iniciados interrompidos, donos sem identidade, mutações sem confirmação, resultados incompletos e renderizadores incertos não têm recuperação automática. Os pedidos, arquivos e marcadores permanecem para inspeção. O worker não é reiniciado automaticamente quando o MCP volta; uma sessão nova consegue explicar os registros anteriores.

Se o resultado foi gravado corretamente mas o host saiu antes de devolver sua vaga, `release_completed` exige dono encerrado, vínculo entre claim/journal, fonte íntegra e confirmação registrada do resultado com hashes dos arquivos — ou cancelamento com saída do filho confirmada. Nenhuma quarentena pode estar presente. A operação só libera a vaga: não recodifica, não reconstrói mídia e não modifica o resultado nem o journal.

## Confirmações tardias

`job_reconcile` usa as mesmas validações de UUID, protocolo explícito, arquivo de nome fixo, limite de bytes, JSON completo e SHA-256 do transporte nativo. Uma confirmação válida não substitui a verificação semântica da ferramenta que perdeu seu processo. Não há promoção de AEP, versão, plano, estado de áudio ou render.

O resultado nativo autenticado pode ser consultado por `native_result_evidence_sha256`, em evidência imutável com a indicação de que a verificação semântica não foi refeita. Journals e arquivos nativos originais permanecem preservados. Não há downgrade automático de protocolo.

A exceção de liberação de quarentena é restrita às ações fixas `inspect`, `design_fonts` e `dependencies_inspect`. Exige dono comprovadamente encerrado, journal e script intactos, intenção registrada, confirmação íntegra, heartbeat da mesma bridge posterior à gravação da confirmação, nenhuma execução ativa, inbox vazia e ausência de quarentena de render. Sob o mutex, o marcador é arquivado byte a byte e sua evidência é persistida antes da liberação. O resultado do serviço perdido continua sem promoção; uma nova consulta protegida pode ser solicitada.

Essa exceção não se aplica a create/build, edição, save, relink ou render, mesmo que exista uma confirmação tardia. Nenhuma rotina de recuperação encerra o AE interativo ou remove `preview-pending.json` de um render incerto. Erros ao publicar o UUID também retêm a intenção: um erro pode ocorrer depois da entrega, portanto não prova que nada executou.

## Cancelamento e fases

O histórico inclui estágio, intenção de lançamento, identidade do filho e saída confirmada. Jobs na fila param antes de executar quando o cancelamento é observado. Codificadores lançados pelo próprio worker podem ser encerrados mediante pedido, preservando saídas parciais. Um pedido durante o render nativo aguarda sua saída ou timeout; pedido recebido não significa trabalho interrompido imediatamente.

No timeout nativo, o marcador e as saídas permanecem. A identidade do processo é diagnóstico, não prova de que todos os processos do engine Adobe terminaram. Não se encerra o AE interativo para recuperar o estado. Cancelamento e erro mantêm logs, cópias e saídas que possam explicar o resultado.

## Dependências e bridge

Por padrão, `project_dependencies` usa a versão salva verificada e a existência atual dos arquivos. Não inclui edições manuais não salvas. Nomes de fontes de ranges sem confirmação de disponibilidade são reportados como não verificados. `refresh: true` lê o projeto solicitado que já está ativo, com confirmação do AE, e informa se inclui mudanças não salvas. Não abre ou salva projetos, não instala fontes/plugins, não relinka e não adiciona raízes de importação.

Efeitos externos podem ser identificados por nome sem que sua instalação ou licença esteja verificada. O relatório distingue essas limitações de mídia/fontes efetivamente ausentes. Mídia externa é apenas identificada; não é copiada ou alterada pela consulta.

O diagnóstico mostra espaço livre, descoberta do executável, donos/filhos, quarentenas e heartbeat. Executável encontrado não prova AE aberto; processo vivo não prova AE saudável. Heartbeat vencido pode significar aplicativo fechado, ocupado ou com modal — o relatório não afirma qual dessas causas ocorreu.

Para uma sessão conhecida expirada, salve o trabalho e execute manualmente o bootstrap já revisado indicado por `bootstrap_script_path` em Arquivo > Scripts > Executar arquivo de script. Havendo operação incerta, inspecione primeiro o job e o AE. Não se repete `-r` automaticamente nem se troca o workspace da sessão.

## Retenção

O plano de limpeza só propõe arquivos antigos de staging atômico de JSON, com nome conhecido, dentro de um job concluído de propriedade identificada. Links simbólicos, links físicos, caminhos fora do job, arquivos grandes, jobs incertos e qualquer quarentena são protegidos. Cada proposta registra tamanho e SHA-256; a operação não remove arquivos.

Todos os AEPs e snapshots, journals, confirmações/evidências, marcadores arquivados, logs, renders, frames, áudio e mídias ficam fora desse plano. A limpeza anterior de frames temporários após decode bem-sucedido de um preview continua com seu contrato próprio; não é uma nova política de exclusão.

O aceite desta sprint é técnico. Não encerra a pendência de transições artísticas da Sprint12, o aceite externo do Claude Desktop9.3, nem inicia EffectCraft.
