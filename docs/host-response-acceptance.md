# Stint 9.3 — diagnóstico e aceitação das respostas no host

## Estado em 08/11/2026

Implementação e aceitação local concluídas; aceitação externa parcial. O operador identificou o host como Claude Desktop e retornou `mcp_runtime.presentation_policy = 9.3` após uma chamada de studio_status nele. Esse é um relato do operador, não captura bruta do protocolo. O operador também confirmou a consulta de fixture no aplicativo: total80, offset0, três itens, next_offset3, nenhuma omissão e sem arrays completos de transforms/keys/samples. A aceitação final das três rotas de edição no host continua pendente; o relato não mede bytes do protocolo. Não encerrar a sprint apenas por testes locais.

O review original continua válido como relato de uma sessão, sem causa atribuída. Não foi comprovado que aquele processo era antigo, solicitava full ou ignorava a política. Não foram reiniciados Claude/AE nem alteradas configurações de aplicativos por este trabalho.

## Mudanças entregues

- studio_status inclui mcp_runtime: processo/runtime UUID, executável Python, caminho/versões do pacote e SDK, política e fingerprint dos arquivos Python/JSX observado no startup MCP.
- Respostas ricas contêm `_meta.astra_presentation`: runtime_id, startup_source_sha256, policy_version, ferramenta e effective_mode. Isso também existe no modo full, sem alterar sua estrutura legada.
- O orçamento compacto inclui essa metadata, além de texto e structuredContent. Não há segunda cópia completa escondida em text. Metadata de diagnóstico não contém argumentos, briefing, ambiente completo nem segredos.
- Os defaults publicados no schema de saída agora indicam compact, alinhados ao schema de entrada e ao comportamento existente. Full continua explícito e preserva o payload legado; o antigo default full no schema de saída era ambíguo, mas não prova a causa do relato.
- Corrigida uma falha real concorrente: Path.resolve no Windows podia retornar um operando com prefixo estendido `\\?\` e outro sem ele. A comparação de caminhos já resolvidos normaliza apenas namespaces de disco/UNC equivalentes; mantém resolução de links e recusa de caminhos externos/device namespaces. Não adiciona raízes nem amplia o alcance de escrita.

Identidade é observada no startup MCP, ou na primeira consulta para uso direto fora do servidor. O hash representa os arquivos naquele instante, não atesta o roteamento do host nem é hash de bytecode carregado. Não recalculá-lo silenciosamente depois de editar arquivos para aparentar atualização de processo antigo. Uma chamada CLI nova também não identifica o MCP que já estava conectado ao Claude.

## Aceitação local

Regressão final: **370 passed, 13 skipped**, em 42,31 s. Testes AE reais não habilitados. O primeiro ensaio no ambiente restrito não conseguiu criar temporários/loop de comunicação local; foi interrompido sem AE e os testes foram executados no ambiente que permite IPC/hard links. A primeira regressão completa encontrou a falha de concorrência; a evidência foi retida, a causa reproduzida e corrigida antes da regressão final.

A fixture usa o servidor/registro/política MCP reais, substituindo explicitamente só LayerService.create, DesignService.apply e MotionService.apply dentro de um subprocesso exclusivo de testes; BridgeRunner.run é proibido nesse processo. Não oferece modo fixture nem executor genérico no servidor de produção.

| Camadas | layer_create compact | text_style_set compact | motion_apply compact |
| --- | --- | --- | --- |
| 3 | 1.885 bytes | 1.887 bytes | 1.885 bytes |
| 5 | 1.889 bytes | 1.891 bytes | 1.889 bytes |
| 40 | 1.899 bytes | 1.901 bytes | 1.899 bytes |
| 80 | 1.899 bytes | 1.901 bytes | 1.899 bytes |

Omissão de response_mode e compact explícito têm os mesmos tamanhos. São bytes de CallToolResult, incluindo as duas representações e metadata, não tokens ou contagem de linhas. Para80 camadas, full explícito fica em aproximadamente2,42 MB por chamada; não é uma resposta padrão.

Foram36 chamadas nas três rotas/quatro tamanhos/três modos, preservando keys/samples/masks/shapes/styles completos e journals na evidência por SHA. Paginação cobre todas as camadas sem perda/duplicação; keys/samples só mediante seção explícita; modo inválido falha antes de criar job.24 respostas compactas somaram45.448 bytes: limite por resposta não torna contexto acumulado ilimitado.

A correção de publicação passou30 rodadas, quatro writers e360 publicações, com um único conteúdo íntegro por rodada e zero falhas. Testes determinísticos também cobrem discos/UNC equivalentes, vizinhos/volumes/servidores distintos e namespace device recusado. O teste de symlink que exige privilégio Windows continua um skip explícito.

Um subprocesso adicional **de produção sem substituir serviços** executou somente studio_status e operation_query de evidência sintética. Páginas: layers14.788 bytes, transforms1.914, keys5.636, samples3.054, todas<=16 KiB. Os três marcadores de pendência consultados permaneceram ausentes antes/depois. Isso não é aceitação de mutação/render AE nem reprodução no Claude Desktop.

Evidências locais:

- [Medições MCP finais](../workspace/stint9-3-9dfac0708d3b4b2ca4c05d6c5053dfcf/acceptance.json), com schemas, argumentos, payloads brutos, hashes, modos e IDs de runtime por processo.
- [Regressão final](../workspace/stint9-3-functional-tests-v2.log); [primeira regressão com falha](../workspace/stint9-3-functional-tests.log).
- [Concorrência corrigida](../workspace/stint9-3-concurrency-fixed-a0cbb9d926eb4678837fd0f41b1b882a/diagnostic.json); [reprodução anterior](../workspace/stint9-3-concurrency-nativefs-2e39a37e6b8345a28ede9642ab278285/diagnostic.json).
- [Produção, leitura apenas](../workspace/stint9-3-production-readonly-0090c2656ce3456893f7a17d79cefbe9/acceptance.json).
- [Referência de fixture para o host](../workspace/stint9-3-host-fixture.json).

As evidências de testes não substituem aceites históricos9.1/9.2 e não reclassificam nenhum render/timeout anterior. O servidor de produção mantém55 ferramentas.

## Conferência no Claude Desktop

1. Na conexão afetada, chamar studio_status e registrar mcp_runtime. Se não aparecer, investigar configuração/processo/checkout antes de qualquer reload. Não reiniciar servidor com jobs pendentes ou ativos; não reiniciar AE para resolver apresentação MCP.
2. Inspecionar list_tools das três ferramentas citadas: response_mode no nível superior tem default compact, tanto input como output. Guardar schema e payload bruto, modo solicitado, metadata de runtime e tamanho de CallToolResult; somente relatos de tamanho estimado não bastam para uma medição em bytes.
3. No mesmo workspace, consultar a fixture abaixo. O resultado é sintético e identificado; não é um AEP nem estado do projeto aberto:

```json
{"request":{"evidence_sha256":"9308c0fe3344659ff11f443b5b95612fc11bbe3743fe0f5150b416b9218920a5","section":"layers","limit":3}}
```

Esperado: total80, três resumos e next_offset3, sem arrays completos de transforms/keys/samples/máscaras. Se evidência não existir, comparar workspace/checkout; não copiar arquivos arbitrários nem modificar raízes por sugestão da ferramenta.

4. A prova das três mutações no host deve usar fixture MCP separada ou projeto descartável previamente preservado/autorizado, nunca repetir uma edição incerta do projeto real. O entrypoint de testes é tests/fixtures/host_response_mcp_server.py; ele exige host-fixture.json dentro de workspace de teste. Executar um novo servidor não troca automaticamente a conexão do Claude.
5. Fechar9.3 somente ao registrar o comportamento no host afetado: compact<=8 KiB, páginas<=16 KiB, full opt-in, evidencia completa íntegra e sem listas não solicitadas. Rotas de mutação testadas apenas via cliente SDK devem continuar rotuladas como prova local. Não pressupor que a versão9.3 identifique a causa da sessão histórica.

As instruções acima são roteiro revisável de aceitação, não autorização para alterar configurações do Claude ou executar mutações nativas. As mutações reais permanecem regidas pelas proteções de workspace, snapshot, IDs, conflito e quarentena.


## Confirmação recebida — consulta no Claude Desktop

O operador informou status succeeded, seção layers, total80, offset0, next_offset3, três itens para limit3 e omitted_oversized_items0. Cada item trouxe só identidade, nome, texto AÇÃO e campos resumidos; sem arrays completos de transformação, keys ou samples. Campos de estado opcionais ficaram null porque não foram preenchidos nessa fixture sintética; isso não diagnostica ausência de propriedades no projeto AE.

O resultado corresponde à paginação/resumo esperados no aplicativo afetado. Fonte: resposta textual do operador, sem payload bruto/medição de CallToolResult. Não transferir as medições locais de bytes para essa confirmação. Evidência: [registro da confirmação](../workspace/stint9-3-claude-query-confirmation.json).

Pendência reduzida: testar layer_create, text_style_set e motion_apply no Claude Desktop por conexão de fixture isolada ou projeto descartável preservado/autorizado, e registrar modo/payload/tamanho. Não repetir operações no projeto aberto para encerrar essa etapa. A causa do relato antigo continua não atribuída; EC-0 não foi iniciada.
