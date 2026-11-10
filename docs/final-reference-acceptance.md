# Aceite final — VÉRTICE

Marca fictícia, peça de24 segundos,1920×1080/30fps. O roteiro segue os intervalos0–6/6–13/13–19/19–24s. A versão vertical só será produzida depois da aprovação explícita do layout paisagem.

## Roteiro

- Abertura: símbolo SVG local convertido em paths nativos, Trim Paths e entrada de título por palavras.
- Mensagem principal: design com propósito, hierarquia tipográfica e um ponto com trajetória espacial Bézier.
- Segunda mensagem: forma/ritmo/significado, precomposição e faixa revelada por matte alpha nativo.
- Encerramento: chamada à ação, símbolo e assinatura editorial. Trilha original sintetizada e acentos sonoros alinhados a eventos nativos.

As cenas são precomposições separadas numa composição principal. As transições passam pelo fundo compartilhado, sem sobrepor títulos de cenas distintas. Motion blur é explícito, com180° de shutter e-90° de fase, nas camadas declaradas. A trilha e os SFX são pós-produção FFmpeg; não ficam embutidos no AEP.

## Estado

Base construída pelo MCP público e reconhecida no AE: cinco composições,29 camadas, fontes ArialMT/Arial-BoldMT resolvidas sem substituição, vetores/keys/matte editáveis e nenhum overflow na inspeção. As versões anteriores mantiveram seus hashes. O roteiro e os assets têm hashes próprios; nenhuma ferramenta de JSX/shell arbitrário foi adicionada ao produto.

O próximo gate é uma intervenção real do operador na posição da camada “Assinatura editorial”, da composição “04 / PRÓXIMO PASSO”, sem salvar o arquivo original pelo AE. O estado manual será capturado por `project_save` numa nova versão antes das duas revisões em português. Uma edição feita por ferramenta não será apresentada como ação humana.

Após a captura e revisões, o filme deve passar por render, contagem de720frames, decode de vídeo/áudio e medição de sincronismo dos acentos no AAC decodificado. Frames de entrada/permanência/transição/saída serão extraídos e só serão declarados vistos depois de realmente abertos. Playback, audição e aprovação artística humana continuam pendentes até confirmação explícita do operador.

Artefatos desta execução: `workspace/final-acceptance-df109fb5616b4c45a5e85c34b9169ba6/`. O arquivo `plan.json` é imutável; `state.json` indica a etapa atual. Os receipts completos de cada chamada estão em `steps/`, além dos journals originais do Astra. O pacote de entrega será gerado e validado depois do render verificado.

Este aceite não inicia EffectCraft e não encerra a pendência externa do Claude Desktop9.3.

## Paisagem verificado; aprovação humana pendente

O operador confirmou a mudança sem salvar. A leitura nativa verificou X=980/Y=940 e que nenhuma outra propriedade mudou; project_save capturou em novo AEP, preservando o disco anterior. As duas revisões em português foram aplicadas e a camada manual permaneceu intacta.

O filme1920×1080/30fps tem720frames/24s e passou por decode completo de vídeo/áudio. A análise do AAC decodificado mediu os quatro SFX com erro0frames na grade de8samples (não precisão infinita); correlações0,739/0,648/0,657/0,719 acima do limiar0,5 fixado antes do teste. Quinze camadas de texto passaram pela verificação geométrica no ponto médio e não houve overflow/substituição.

Foram realmente vistos16frames de entradas, holds, transições, saídas e intervalos revisados. Os títulos de cenas distintas não se sobrepõem nas amostras; a curva e a faixa com matte aparecem corretamente. Isso não certifica playback/audição completos. O pacote foi coletado, reaberto e validado, incluindo hashes e reconstrução de áudio. Os assets originais também acompanham a entrega em pasta separada.

Preservados1.164 AEPs gerenciados anteriores e70 versões desta construção/captura/revisões. Evidência:landscape-acceptance.json no diretório da execução. A aprovação humana do paisagem e a adaptação vertical continuam pendentes; o plano original não foi alterado.

## Feedback e revisão de eficiência — 2026-11-10

O operador pediu melhora dos SFX e maior suavidade das curvas, especialmente na segunda parte, além de revisão do custo das chamadas. O feedback não encerra o gate artístico do paisagem. A revisão encontrou chaves temporais lineares no ponto da trajetória e um mesmo chirp agudo repetido nas quatro entradas. Recomendações e limites estão em [revisão de criação](creation-optimization.md).

A otimização adicionou criação inicial agrupada e respostas menores, verificadas em fixtures separadas. O roteiro foi atualizado para lotes por cena e resolução local de evidência; o build completo otimizado não foi reexecutado. Nenhum plano/receipt/pacote/render histórico foi substituído. A revisão artística dos SFX/curvas do VÉRTICE ainda não foi aplicada; aprovação paisagem e vertical permanecem pendentes.
