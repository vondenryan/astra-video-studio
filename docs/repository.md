# Versionamento do Astra Video Studio

Repositório: https://github.com/vondenryan/astra-video-studio

A branch `main` contém o código Python/JSX, testes, documentação, roadmap, instruções de trabalho, dependências e `.env.example`. O commit inicial existente e sua licença foram preservados.

O `.gitignore` exclui o ambiente `.venv`, caches, configurações `.env`, logs, pastas temporárias, `deliveries/` e todo o `workspace/`. O workspace reúne projetos AEP, snapshots, mídia, renders, filas, evidências e estado da sessão AE; esses arquivos continuam preservados localmente e precisam de backup próprio. Referências a eles nos relatórios documentam o aceite local e não significam que estejam disponíveis num clone do GitHub. Nunca restaurar uma sessão AE copiando apenas o código ou apagando marcadores de execução pendente.

Para instalar uma cópia nova no Windows, siga [instalação](installation-windows.md). Defina um workspace local próprio e os caminhos do AE/FFmpeg. Não copie configurações de autenticação para o repositório. O código não inclui fontes, plugins ou binários de terceiros.

A validação funcional mais recente antes do primeiro envio foi `480 passed / 19 skipped`. A criação agrupada também passou em testes opt-in no AE; escopos e limites em [relatório de testes](test-report.md) e [otimização](creation-optimization.md). O envio ao GitHub não adiciona novo aceite nativo ou artístico.
