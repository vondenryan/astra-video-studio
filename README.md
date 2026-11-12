# Astra Studio

O Astra Studio conecta assistentes compatíveis com MCP ao Adobe After Effects para criar, organizar e revisar projetos de motion design com elementos nativos editáveis.

O assistente usa ferramentas com parâmetros definidos; o Astra executa as operações localmente, verifica o resultado no After Effects e mantém versões do projeto. A comunicação funciona por **MCP via stdio**, com uma CLI para diagnóstico e operações locais.

## Recursos

O servidor oferece **77 ferramentas**, organizadas nas seguintes áreas:

| Área | Capacidades |
| --- | --- |
| Projetos | Criar projetos, abrir cópias de AEPs existentes, inspecionar composições e capturar alterações manuais. |
| Cenas e camadas | Criar composições, precompor, duplicar e organizar camadas, configurar parentesco 2D e track mattes. |
| Texto e design | Aplicar tipografia com fontes instaladas, estilos por intervalo, animadores de texto, tokens e layouts. |
| Vetores | Criar paths Bézier, importar um subconjunto de SVG, configurar preenchimentos, contornos, Trim Paths e morphs compatíveis. |
| Animação | Aplicar movimentos, agrupar animações, editar keyframes, ajustar easing e tangentes, retimar intervalos e configurar motion blur. |
| Direção | Transformar briefs em planos e storyboards estruturados e aplicar revisões pontuais em português. |
| Áudio | Inspecionar assets, montar clips com ganho e fades, definir cues e verificar sincronismo em estados de áudio versionados. |
| Render e entrega | Gerar prévias, submeter renders finais, coletar projetos e mídia e validar pacotes de entrega. |
| Revisões | Planejar alterações, detectar conflitos, comparar versões e restaurar versões anteriores em novos arquivos. |
| Operação | Consultar jobs, fila, dependências e diagnósticos de recuperação. |

## Como funciona

```text
Assistente compatível com MCP
            |
      Astra Studio
       /         \
Bridge local    FFmpeg / FFprobe
     |
After Effects
     |
Workspace: projetos, versões e evidências
```

O servidor Python recebe solicitações estruturadas e gera operações a partir de templates controlados. A bridge local entrega essas operações ao After Effects. O Astra exige uma confirmação correspondente e verifica os artefatos antes de considerar a operação concluída.

As alterações são salvas em novas versões. Snapshots, identificadores persistentes e hashes permitem acompanhar o histórico e verificar se as propriedades esperadas foram preservadas. O áudio é processado pelo FFmpeg em arquivos e planos separados; não é embutido automaticamente no AEP.

## Requisitos

- Windows 11 e Adobe After Effects 2025. O ambiente nativo verificado utiliza AE 25.5.
- Python 3.11 ou superior.
- FFmpeg com `libx264` e FFprobe disponíveis no computador.
- Permissão do After Effects para scripts gravarem arquivos e acessarem a rede.
- Um cliente compatível com servidores MCP locais via stdio.

O Astra não exige chave de API própria nem serviço pago adicional. O modelo e o cliente usados para conversar com o assistente são configurados separadamente.

## Instalação

No PowerShell:

```powershell
git clone https://github.com/vondenryan/astra-video-studio.git
cd astra-video-studio
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\astra-studio.exe status
```

Configure os caminhos de acordo com a instalação local:

```powershell
$env:ASTRA_WORKSPACE = Join-Path (Get-Location) 'workspace'
$env:ASTRA_AE_EXECUTABLE = 'C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe'
$env:ASTRA_FFMPEG = 'C:\ffmpeg\bin\ffmpeg.exe'
$env:ASTRA_FFPROBE = 'C:\ffmpeg\bin\ffprobe.exe'
```

Essas variáveis valem para a sessão atual. Configure-as também no cliente MCP quando ele iniciar o servidor. O arquivo [`.env.example`](.env.example) documenta as opções disponíveis; o Astra não carrega arquivos `.env` automaticamente.

## Conexão MCP

Cadastre um servidor local no cliente de sua preferência. Exemplo de configuração — substitua os caminhos pelos da sua instalação:

```json
{
  "command": "C:\\Projetos\\astra-video-studio\\.venv\\Scripts\\python.exe",
  "args": ["-m", "astra_video_studio.mcp_server"],
  "env": {
    "ASTRA_WORKSPACE": "C:\\Projetos\\astra-video-studio\\workspace",
    "ASTRA_AE_EXECUTABLE": "C:\\Program Files\\Adobe\\Adobe After Effects 2025\\Support Files\\AfterFX.exe",
    "ASTRA_FFMPEG": "C:\\ffmpeg\\bin\\ffmpeg.exe",
    "ASTRA_FFPROBE": "C:\\ffmpeg\\bin\\ffprobe.exe"
  }
}
```

O formato externo da configuração depende do cliente. O Astra não altera as configurações dos aplicativos automaticamente. Logs usam stderr; stdout fica reservado ao protocolo MCP.

## Inicialização da bridge

Com o trabalho atual salvo e o After Effects aberto, inicialize a bridge:

```powershell
.\.venv\Scripts\astra-studio.exe bridge-start
```

Se a inicialização não for confirmada, consulte `studio_status`: o campo `bridge_runtime.bootstrap_script` indica o script que deve ser executado em **Arquivo > Scripts > Executar arquivo de script** no After Effects. Após a confirmação, as operações reutilizam a fila local.

Use um único workspace por sessão do AE. Se houver uma operação pendente ou sessão expirada, inspecione o estado antes de reinicializar; não repita comandos nem remova marcadores de execução para forçar a continuidade.

## Uso eficiente

- Comece por `studio_status` para consultar a configuração e o estado da bridge.
- Use `layers_create` para criar até 20 camadas com tipografia inicial em uma única operação verificada.
- Use `motion_batch` para agrupar movimentos compatíveis.
- Consulte apenas as composições, camadas e propriedades necessárias com `project_query` e `operation_query`.
- Mantenha o cliente MCP ativo até a conclusão dos jobs em fila.

As respostas são compactas por padrão, com limite de **8 KiB** nos resultados ricos. Automações podem solicitar `response_mode="receipt"`, limitado a **3 KiB**, e recuperar os detalhes pela evidência verificada. O modo `full` é explícito e mantém a saída completa para compatibilidade e diagnóstico. A redução das respostas não remove as verificações internas.

## Preservação e limites

O Astra trabalha em cópias e novas versões, mantendo os arquivos de origem. Alterações manuais precisam ser capturadas explicitamente quando necessário; conflitos de versão ou de propriedade podem bloquear a operação.

O escopo de edição é principalmente 2D. Expressões, tracks automáticos e operações fora dos contratos implementados têm proteções específicas. A importação SVG aceita um subconjunto definido e não converte recursos incompatíveis silenciosamente em imagens. Fontes e plugins precisam estar instalados; não são distribuídos com o projeto.

Jobs incertos ficam protegidos para inspeção. O Astra não mata o After Effects nem reenvia automaticamente uma operação cujo resultado seja desconhecido. Verificação técnica e revisão artística são etapas distintas.

Um motor alternativo baseado no EffectCraft está em avaliação experimental isolada. O quinto marco comparou um gráfico estático e uma curva de opacidade com evidência arquivada do After Effects e diagnosticou 17 projetos sintéticos AEP/AEPX. O Astra usa o After Effects como backend padrão. [Andamento da EC-0](docs/effectcraft/ec0-progress.md)

O sexto marco executou o alvo de integração AEP do upstream com o corpus obrigatório. Foram 602 testes aprovados e cinco ignorados pelo upstream. A avaliação continua com comparação visual ampliada, desempenho, memória e licenças pendentes.

A avaliação cobre persistência, fontes fixadas, animação de texto, curvas manuais e composição CPU com efeitos, importação SVG editável, máscaras e mattes. A comparação com o After Effects segue como etapa da avaliação.

## Desenvolvimento

Execute a suíte funcional:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes nativos do After Effects ficam desabilitados por padrão. Sua ativação explícita cria projetos reais e pode deixar uma nova versão aberta; consulte a documentação antes de executá-los.

O repositório contém código, testes e documentação. O workspace de execução, AEPs, renders, mídias, ambiente Python e caches ficam fora do Git e precisam de backup separado.

## Documentação

- [Instalação detalhada](docs/installation-windows.md)
- [Arquitetura](docs/architecture.md)
- [Contratos das ferramentas](docs/tool-contracts.md)
- [Edição de cenas](docs/scene-editing.md)
- [Tipografia, vetores e layouts](docs/design-tools.md)
- [Editor de animação](docs/animation-editor.md)
- [Revisões e colaboração manual](docs/revisions.md)
- [Storyboard e direção](docs/storyboard-director.md)
- [Áudio e sincronização](docs/audio-tools.md)
- [Render final e entrega](docs/final-delivery.md)
- [Fila e recuperação](docs/recovery.md)
- [Respostas compactas](docs/compact-responses.md)
- [Roadmap](ASTRA_VIDEO_STUDIO_PRO_ROADMAP.md)

## Licença

[MIT](LICENSE).
