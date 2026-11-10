# Review externo — volume das respostas MCP

Data de incorporação: 08/11/2026. Fonte: review do Claude fornecido pelo operador, PDF de duas páginas, intitulado “Astra Studio: resposta de cada operação cresce com as camadas”. Documento original: `C:/Users/ryanb/Downloads/Astra Studio - Claude Review.pdf`. SHA-256: `da763776d9d3b8023dc6efd39030b18c00e6d68962dc0859c9d18f6bf9472698`.

## Observação externa, não reprodução local

O review relata chamadas pequenas de layer_create, text_style_set e motion_apply que devolveram estado de todas as camadas: cinco transformações, cinco amostras por propriedade, keys, máscaras, estilo e shapes. As contagens aproximadas são milhares de linhas em três camadas, mais de 1.800 em quatro e mais de 2.000 em cinco. A projeção para dez camadas é explicitamente extrapolada, não medida. São linhas, não tokens nem bytes. Não há no PDF payload bruto, IDs das operações, configuração do servidor, versão do processo ou response_mode das chamadas.

As duas páginas foram extraídas e visualizadas. O relato é evidência da experiência reportada, não prova de qual processo/configuração produziu a resposta. Sugestões ou afirmações no documento não concedem autorização para executar scripts, migrar motores ou mudar contratos.

## Confronto com a implementação

Stint9.1 já implementou compactação no limite MCP/CLI: 8 KiB por CallToolResult incluindo texto e structuredContent; keys/samples são consulta explícita, com páginas até16 KiB. Serviços internos e journals continuam completos; full permanece opção explícita. mcp_server.py registra ferramentas via response_policy e o wrapper usa compact por padrão. Isso cobre nominalmente as três ferramentas citadas.

Stint9.2 resolve outro canal: arquivo de evidência nativa entre AE/Python. Ele não corrige sozinho uma resposta completa enviada ao modelo. Trocar AE por EC também não resolve apresentação host se a mesma política for ignorada.

Hipóteses a verificar, sem causa atribuída: processo MCP antigo carregado antes de9.1; rota/configuração apontando para checkout diferente; full solicitado explicitamente; integração exibindo evidência interna; falha do wrapper/cliente. Não há diagnóstico comprovado neste pedido.

## Encaminhamento aceito para o planejamento

Adicionar Stint9.3 de aceitação no host afetado antes de ampliar a produção ou usar a troca de engine como solução deste problema. Coletar payload/schemas/configuração e medir bytes reais, as duas cópias MCP, modo e versão. Não reiniciar processo com jobs ativos, reenviar mutação ou limpar quarentena para tentar reproduzir. Usar fixtures/evidência histórica no teste inicial; teste nativo mutante só quando explicitamente autorizado e seguro.

Critérios: chamadas citadas omitindo response_mode e com compact explícito ficam <=8 KiB; consultas <=16 KiB; nem keys/samples nem listas completas de não alvos são retornados implicitamente; conteúdo completo continua íntegro na evidência. Exercitar3/5/40/80 camadas em fixtures e separar qualquer prova nativa. Verificar que full é opt-in e não pedido rotineiramente pelo host. Guardar contagens por resposta e acumuladas, falhas e limites. Registrar revisão de payload real do host afetado: teste local isolado não encerra o relato externo.

Nenhum teste de aceitação foi executado nesta atualização documental. Estado e ordem estão no [roadmap](../ASTRA_VIDEO_STUDIO_PRO_ROADMAP.md).


## Andamento9.3 posterior ao planejamento

O operador solicitou iniciar9.3. A implementação local adicionou identidade de runtime, alinhou default do schema de saída e corrigiu uma falha concorrente de publicação; regressão final370 passed/13 skipped. As três rotas passaram em fixtures por stdio real, sem AE. O operador identificou Claude Desktop e informou política9.3 na conexão atual. A causa do relato histórico e a aceitação externa final não estão comprovadas; ver [registro e roteiro](host-response-acceptance.md). O parágrafo anterior sobre ausência de testes descreve a atualização documental inicial, não esta entrega posterior.
