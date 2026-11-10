# Revisão de criação e eficiência — 2026-11-10

O gargalo encontrado no roteiro VÉRTICE tinha duas causas evitáveis: pedir estado completo em todas as chamadas e criar/formar textos em operações separadas. A revisão mantém snapshots, confirmação do AE, evidência completa, proteção de edições manuais e comparação dos não alvos.

## Medição e limites

Reconstrução dos envelopes de resultado a partir dos 70 receipts imutáveis do build original, incluindo texto, `structuredContent`, metadados e referência de evidência:

| Modo | Bytes nos 70 resultados | Redução frente ao completo |
| --- | ---: | ---: |
| `full` | 14.662.657 | — |
| `compact` | 243.558 | 98,3% |
| `receipt` | 104.126 | 99,3% |

Isso é reconstrução de conteúdo, não captura histórica do protocolo. Não inclui definições das ferramentas, requests, framing JSON-RPC nem contexto/conversa do modelo. Não é uma medição de tokens ou aceleração do vídeo inteiro. O modo compacto já existia; o roteiro solicitava `full` explicitamente. O primeiro ganho vem de usar a política existente corretamente.

Ensaio nativo controlado: três textos com fonte/alinhamento/leading explícitos e duas formas. O caminho separado fez oito mutações em 37,39s; `layers_create` fez uma em 4,69s. Ganho observado ~8× nesse trecho, numa execução por caminho, sem alegar mediana/p95 ou ganho equivalente de render. Os metadados visuais coincidiram e a camada sentinela ficou idêntica. Dois renders H.264 de seis frames/320×180 passaram por decode completo; o primeiro PNG decodificado de cada um tem o mesmo SHA-256. É equivalência dessa fixture estática, não aprovação artística ou equivalência de todo o filme.

Fontes ausentes e overflow foram recusados no AE sem promover a versão; o overflow síncrono preservou a cópia falha e reabriu a fonte limpa. O conjunto inicial de 1.234 AEPs foi preservado por hash; a validação seguinte preservou os 1.245 então existentes. O transporte nativo, sua quarentena e os limites de render não foram reduzidos.

Evidências preservadas:

- `workspace/optimization-audit/462acb3d02284371a9071b776d966309/audit.json`.
- `workspace/optimization-acceptance/25e88d556ac548ad8be80286de138932/acceptance.json` e `render-check.json`.
- `workspace/optimization-acceptance-current.json`: aponta o ensaio nativo final, incluindo a proteção de concorrência de toda a operação agrupada.
- `workspace/optimization-functional-tests.log` e `workspace/optimization-native-final-tests.log`.

## Implementações

**`response_mode="receipt"`** é opcional para resultados ricos MCP/CLI. O envelope completo, incluindo texto duplicado e `_meta`, fica limitado a 3 KiB; conserva status/ID/referência hash e poucos IDs operacionais. `compact` continua padrão com 8 KiB; `full` mantém o payload estruturado legado intacto. Polling em receipt omite eventos e resultado aninhado; a evidência mantém tudo. Falha de apresentação nunca significa autorização para reenviar a operação.

**`local_client.resolve_response(settings, response)`** permite a um controlador local obter os detalhes pelo arquivo imutável, sem nova chamada MCP nem envio do estado inteiro ao modelo. Deriva o caminho exclusivamente do SHA, verifica contenção, tamanho, hash, schema e identidade/status e verifica novamente o hash após a leitura. Não confia no caminho recebido e não faz retries. Requer acesso local ao mesmo workspace; não é uma ferramenta de leitura arbitrária para clientes remotos. Clientes sem esse acesso usam `compact` e consultas filtradas quando necessário.

**`layers_create`** cria 1–20 camadas nativas numa composição, com textos/formas/sólidos e tipografia inicial exata. Exige hash da fonte salva, recusa estado sujo, gera UUIDs e uma nova versão/snapshot, verifica tudo depois de reabrir e compara os não alvos. Mantém o mutex do AE desde a leitura do head até a promoção; admite fontes exatas, não mídia ou scripts livres. Os itens seguem a ordem das chamadas de criação: o último fica acima. Não edita animação existente. O compacto devolve o mapa limitado `role → layer_id`; `operation_query(section="created_layers")` recupera o mapa pela evidência se necessário. Falha/timeout nunca promove a versão. Não há rollback automático de timeout.

O roteiro local de aceite foi atualizado para receipt com leitura verificada local e quatro lotes de criação, um por cena. Isso reduz estaticamente seu build de 70 para 37 chamadas: as 38 criações/formatações passam a cinco chamadas (fundo + quatro lotes). O build completo otimizado não foi reexecutado nem apresentado como novo filme aceito. O plano, os receipts, o pacote, a edição manual e o render originais continuam preservados.

## Fluxo recomendado

1. Fixar brief, cenas, textos, paleta, fontes instaladas e cues antes de criar camadas. Guardar IDs retornados; não redescobrir o projeto completo a cada passo.
2. Criar as camadas de cada cena em lote com sua tipografia. Usar os IDs para vetores/mattes e o `motion_batch` já existente para animações independentes.
3. Usar compacto com clientes de conversa; usar receipt + resolver local em controladores locais. Consultar somente a camada/propriedade necessária; keys/samples explícitos.
4. Preservar as inspeções completas internas por transação. Não reutilizar uma inspeção antiga para autorizar escrita nem ignorar edição manual para ganhar tempo.
5. Verificar trecho curto quando houver risco visual de tipografia/curva/matte. Render completo depois das revisões aprovadas; uma submissão por job, polling limitado e sem repetir jobs incertos.
6. Aprovar imagem/ritmo/áudio com revisão humana. Hashes, decode e frames amostrados têm escopos diferentes dessa aprovação.

## Qualidade: SFX e curva da segunda cena

Feedback do operador: melhorar o SFX e suavizar a curva, especialmente na segunda parte. Esse feedback não foi registrado como aprovação artística final do paisagem. A adaptação vertical permanece pendente.

**Curva:** as três posições do ponto na segunda cena têm tangentes espaciais curvas, porém tipos temporais Linear nas chaves 30/90/150. O traçado e a evolução da velocidade são controles diferentes. A revisão candidata deve suavizar saída/chegada com Bezier temporal, manter velocidade não nula e compatível na chave intermediária e preservar tempos, valores, tangentes espaciais, boundaries e não alvos. Não aplicar velocidade zero a toda chave intermediária: isso pode criar uma parada perceptível. Medir deslocamento/velocidade por frame perto das junções e assistir ao trecho antes de aprovar. Os controles atuais `easing_set`/`motion_path_set` já permitem essa correção com guards; falta uma receita de direção e QA de velocidade, não um novo executor livre.

**SFX:** o asset original é um chirp agudo (~3,4 kHz no ataque), com ataque ~3ms e decaimento curto, repetido quatro vezes a -5dB. É um diagnóstico do gerador e dos clips, apoiado no feedback humano; não uma nova avaliação de audição do agente. A proposta é criar variações com função definida (entrada, passagem, revelação, assinatura), ataque menos abrupto, menos energia aguda e menor destaque na mix, preservando cues/sincronismo. Selecionar ouvindo junto da trilha e fazer A/B; baixar volume sozinho não comprova melhora artística. Gerar novo estado de áudio explicitamente ligado ao novo AEP se houver revisão de animação. Não alterar/rebasear o estado antigo implicitamente.

Essas revisões artísticas do filme ainda não foram aplicadas por esta otimização. Não houve novo render VÉRTICE, audição ou aprovação final alegados.

## Próximas prioridades

1. Receita de curvas de velocidade contínua nos pontos de passagem, com amostras ao redor das chaves e preview A/B. Preservar proteções de expressão/auto/continuous/roving.
2. Biblioteca pequena de SFX por função e variantes de intensidade, com escolha/mix/cues declarados e comparação auditiva. Os clips, fades, sync e verificações de pico já existem; curadoria e direção sonora ainda precisam evoluir.
3. Medir por fase (planejamento, mutações, render, encode, revisão) e repetir os benchmarks para mediana/p95 antes de prometer aceleração geral. O ganho medido aqui é de transporte e criação inicial.
4. Só depois considerar lotes tipados de paths/estilos/áudio e perfis menores de ferramentas. Medir custo de schema/requests e uso real antes de ampliar a API. Não paralelizar chamadas à mesma sessão AE nem remover verificações internas.

EffectCraft continua adiado; o aceite externo das rotas de edição Claude Desktop 9.3 permanece separado.
