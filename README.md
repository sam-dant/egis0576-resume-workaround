# EgisTec EH576 — sincronização após suspend/resume

**Português** | [English](README.en.md)

Workaround para o leitor **EgisTec EH576 (`1c7a:0576`)**: pausa o `fprintd` antes da suspensão, reautoriza o USB no retorno e bloqueia ativações antecipadas do daemon até concluir essa operação.

Este projeto **não instala nem modifica o driver**, o PAM, cadastros biométricos, regras de energia ou o modo de suspensão. O driver é um projeto independente: [PHILIPPDEV5396/libfprint-egis0576](https://github.com/PHILIPPDEV5396/libfprint-egis0576). Cadastro e autenticação devem funcionar antes de instalar este workaround.

## Origem e estado de validação

A solução de referência foi relatada como estável por vários dias em um **Lenovo IdeaPad Flex 5 14ITL05, Zorin OS 18.1, GNOME/GDM, s2idle**, com vários ciclos de suspensão, tampa e desbloqueio biométrico. Os sintomas incluíam `Device was already claimed` e `Device 1c7a:0576 is already open`; reiniciar manualmente o `fprintd` restaurava a operação. A investigação relatada identificou uma corrida entre a ativação do daemon e a recuperação do USB.

Os scripts deste repositório foram escritos a partir desse relato. **Esta versão empacotada passou por uma validação inicial no hardware de referência em 13/09/2026, com o driver v0.4.3 (`5448ab7`).** Com apenas o hook oficial do driver, a digital não era oferecida após suspensão; depois de instalar este pacote, o usuário confirmou funcionamento ao suspender pelo menu e fechar/abrir a tampa. A estabilidade prolongada e os caminhos de falha ainda precisam de validação física. A v0.4.4 não foi testada. Os testes automatizados usam arquivos temporários e comandos simulados; não reproduzem o kernel USB, o agendamento do systemd, D-Bus ou GDM. O commit do driver usado na validação original, informado pelo usuário do sistema de referência, foi [7849db90c37131b0662e7e17059caebfb9b277c7](https://github.com/PHILIPPDEV5396/libfprint-egis0576/commit/7849db90c37131b0662e7e17059caebfb9b277c7). Essa referência registra a versão utilizada; não constitui uma verificação do binário instalado nem uma garantia de compatibilidade com outros commits.

Uma inspeção somente leitura confirmou configurações locais e identificou diferenças do helper e cópias de hooks: veja [sistema de referência](docs/reference-system.md). A regra udev existente mantém `power/control=on`; ela não é gerenciada por este projeto.

Decisões preservadas:

- Não executar `systemctl restart fprintd` no `post`. Essa tentativa piorou o comportamento no GDM e gerou warnings do libusb no sistema de referência.
- Manter ativação normal por D-Bus/GDM depois da remoção do marker.
- Permanecer em **s2idle**. O teste com `deep` travou o notebook de referência e exigiu desligamento forçado. O instalador recusa outro modo selecionado e não o altera.

## Funcionamento

1. `pre suspend`: cria `/run/egis0576-fprintd-resume.pending`, depois para `fprintd.service` com limite de 15 segundos. Marca a etapa como pronta somente se a parada tiver sucesso.
2. `post suspend`: exige que o `pre` tenha concluído, procura exatamente um USB `1c7a:0576` por até aproximadamente 10 segundos, escreve `0` no atributo `authorized`, espera **1,5 segundo**, escreve `1` e remove o marker.
3. O drop-in adiciona `ExecStartPre=/usr/local/sbin/egis0576-fprintd-wait`. Enquanto o marker existir, esse helper aguarda; ao desaparecer, permite a partida normal do daemon.

O uso do atributo `authorized` segue a [documentação USB do kernel](https://www.kernel.org/doc/html/latest/usb/authorization.html). Não há reset do controlador, de hubs ou de outros dispositivos USB.

As proteções adicionadas ao empacotamento são: parada e espera limitadas, recusa de múltiplos leitores, nova tentativa de localização do USB e tentativa de reautorização em caso de erro durante a pausa. Se algo falhar, o marker é mantido e o helper **falha após aproximadamente 30 segundos**, sem liberar a partida do daemon. O helper nunca remove o marker. Isso pode tornar a biometria indisponível até a recuperação; use a senha.

Os hooks são destinados apenas a `suspend`. Hibernação, suspensão híbrida e `suspend-then-hibernate` não são suportados. Falhas de um hook não devem ser consideradas um mecanismo para cancelar a suspensão. O marker não é um teste de saúde do leitor: uma escrita bem-sucedida em `authorized` não garante que o firmware ou o driver estejam prontos em qualquer máquina.

## Arquivos

| Origem | Destino instalado |
| --- | --- |
| `systemd/system-sleep/50-egis0576-fp-resume.sh` | `/usr/lib/systemd/system-sleep/50-egis0576-fp-resume.sh` |
| `scripts/egis0576-fprintd-wait` | `/usr/local/sbin/egis0576-fprintd-wait` |
| `systemd/fprintd.service.d/10-egis0576-resume.conf` | `/etc/systemd/system/fprintd.service.d/10-egis0576-resume.conf` |

`install.sh` e `uninstall.sh` usam o backend Python `lib/manage.py`. Os scripts instalados usam apenas Bash, systemctl e utilitários básicos. O diagnóstico é executado da cópia do projeto; não é instalado no sistema.

## Pré-requisitos e instalação

Requer Linux com systemd em execução, Bash, Python **3.8+**, GNU coreutils (`timeout`, `sleep`, `rm`), serviço `fprintd.service` carregável e exatamente um EH576 já autorizado. Precisa estar selecionado `[s2idle]` em `/sys/power/mem_sleep`. Distribuições imutáveis ou que usam outra localização de hooks precisam de adaptação; não são alvos desta versão.

### É necessário baixar algo mais?

O workaround é autocontido: **não há dependências pip/npm, submódulos nem etapa de compilação**. A instalação não baixa nada e pode ser executada offline quando o projeto e os pré-requisitos do sistema estiverem disponíveis. O código Python usa somente a biblioteca padrão.

O driver libfprint com suporte ao EH576 e o `fprintd` precisam estar instalados e funcionando; são pré-requisitos separados e não estão incluídos. Se já funcionam no seu sistema, este projeto não exige baixá-los ou reinstalá-los.

**ShellCheck é opcional para desenvolvimento local**, não para executar o workaround. Se estiver ausente, `scripts/check.sh` ainda executa a verificação de sintaxe Bash e os testes Python. O workflow do GitHub Actions baixa a action de checkout e instala ShellCheck via apt no executor do CI, portanto esse workflow precisa de rede. Git é útil para controle de versão, mas não é uma dependência do instalador. O diagnóstico também usa ferramentas padrão do sistema, incluindo `journalctl`, `grep` e `sha256sum`.

Primeiro confirme cadastro e autenticação usando o driver e verifique que consegue entrar com **senha**. Salve seu trabalho e mantenha a máquina acordada durante instalação/desinstalação; não execute essas operações durante um ciclo de suspensão.

Na pasta do projeto:

```bash
./scripts/check.sh
sudo ./install.sh --check
sudo ./install.sh
```

`--check` executa a pré-verificação sem instalar arquivos nem recarregar o systemd. Ela exige root para verificar a permissão de escrita no USB. A instalação efetiva altera apenas os três arquivos acima, cria o registro de backup em `/var/lib/egis0576-resume`, usa um lock em `/run` e executa `systemctl daemon-reload`. Não inicia, para nem reinicia o daemon durante a instalação.

Se a solução original já estiver nos **três destinos exatos**, revise esses arquivos e use:

```bash
sudo ./install.sh --check --replace-existing
sudo ./install.sh --replace-existing
```

Os conteúdos, permissões, UID e GID anteriores serão preservados para restauração. Não são preservados ACLs, atributos estendidos nem rótulos SELinux personalizados; a instalação foi direcionada ao ambiente Zorin descrito. Destinos ou diretórios ancestrais que sejam symlinks são recusados.

O instalador recusa instalação já registrada, marker pendente, hardware ausente/ambíguo, USB não autorizado, `fprintd` ausente/mascarado, modo diferente de s2idle e algumas personalizações incompatíveis do serviço. Também procura referências a Egis/fprint/USB reset em outros hooks e drop-ins. **Essa busca é heurística e não cobre toda configuração possível**: revise `systemctl cat fprintd.service` e os hooks locais.

O [projeto do driver](https://github.com/PHILIPPDEV5396/libfprint-egis0576) também fornece integração de suspensão. Um hook concorrente precisa ser revisado e desativado manualmente antes desta instalação. `--replace-existing` só autoriza substituir os três destinos deste projeto; não ignora conflitos com outros arquivos. Não remova a biblioteca do driver para resolver esse conflito.

## Teste físico: suspend → resume → lock → fingerprint

Faça o teste sem cadastro ou verificação biométrica em andamento. Registre versões de kernel, distribuição, driver/commit e desktop.

1. Antes da primeira suspensão, confirme a autenticação normal e a alternativa por senha. Confira `cat /sys/power/mem_sleep` e `systemctl cat fprintd.service`.
2. Suspenda pelo menu do desktop, retome e confirme que o marker desapareceu: `test ! -e /run/egis0576-fprintd-resume.pending` deve retornar código zero.
3. Bloqueie a sessão pela interface do desktop e desbloqueie com a impressão digital. Se o retorno já estiver bloqueado, teste ali também; use senha se necessário.
4. Repita pelo menos cinco ciclos. Teste também bloquear **antes** de suspender, fechar/abrir a tampa e retomar conectado/desconectado da tomada. Espere cada autenticação terminar antes de repetir.
5. Capture `sudo ./scripts/diagnose.sh` após os testes. Procure falhas de inicialização, marker persistente, timeouts e repetição dos erros de claim/open. Não deve haver restart explícito do daemon no `post`.
6. Em uma janela de manutenção, teste desinstalar e confirme a restauração dos arquivos anteriores. Reinstale se quiser continuar usando o workaround.

Um `fprintd` inativo enquanto ocioso não é, isoladamente, falha: a ativação é por demanda. Não há fluxo automático que bloqueie a tela, suspenda a máquina ou tente autenticar pelo usuário.

## Diagnóstico e troubleshooting

```bash
sudo ./scripts/diagnose.sh > diagnostics-local.txt 2>&1
```

O diagnóstico é somente leitura: mostra OS/kernel, modo de suspensão, atributos relevantes do EH576, marker, unidade efetiva, estado e logs do boot atual. Não lê templates biométricos nem invoca clientes que ativam o leitor. Revise nomes de usuário, hostname e demais dados pessoais antes de compartilhar os logs.

**Marker persistente ou helper expirando:** entre com senha, capture o diagnóstico e confira as mensagens `egis0576-resume` no journal de `systemd-suspend.service`. Não apague o marker enquanto uma recuperação estiver em andamento. O conteúdo `stopping` indica que o `pre` não concluiu; `ready` indica que a parada foi concluída, mas a recuperação ainda não removeu o marker. O conteúdo não prova que o hook continua em execução.

Após salvar seu trabalho e coletar os logs, **reiniciar o computador** é a recuperação mais simples: `/run` é temporário e o dispositivo passa pela inicialização normal. Isso também permite tentar a desinstalação se um marker pendente a estava impedindo. Se o problema se repetir, desinstale e investigue o driver/USB antes de continuar os testes. Uma entrada automática em suspensão logo após o boot pode recriar o problema: mantenha a sessão acordada durante a manutenção.

**Erros de claim/open continuam sem marker:** confira se há outro hook ou drop-in, registre a versão do driver e verifique se o problema existe antes de suspender. Reiniciar manualmente `fprintd` foi uma recuperação observada na investigação original; isso não deve virar um restart automático no hook `post`.

**Leitor desaparecido ou reautorização falha:** o hook mantém a barreira. Confira os logs de USB; não altere `authorized` de hubs ou de outro USB ID. A correspondência desta implementação é exata para `1c7a:0576`.

**Falha na instalação/desinstalação:** preserve `/var/lib/egis0576-resume/active.json` e os arquivos atuais. O instalador tenta rollback automático quando ocorre uma exceção durante a instalação. Se o rollback ou o reload também falhar, o registro permanece para recuperação. Depois de resolver a causa, execute `sudo ./uninstall.sh`: ele aceita arquivos já restaurados e pode retomar uma restauração interrompida. Interrupções abruptas e falhas de armazenamento podem exigir recuperação manual; o backup não é uma garantia contra perda física de dados.

## Desinstalação, rollback e atualização

```bash
sudo ./uninstall.sh
```

A desinstalação restaura o conteúdo e os metadados básicos anteriores de cada destino; remove somente arquivos que não existiam antes. Diretórios criados podem permanecer vazios. Ela recarrega o systemd e não reinicia o daemon. Portanto, se havia um workaround anterior, **ele volta a estar instalado**.

Os registros JSON contêm o conteúdo original em Base64 e hashes SHA-256 do conteúdo instalado. São salvos com permissão `0600`. Após sucesso, `active.json` é renomeado com data UTC e sufixo `uninstalled` ou `rolled-back`, preservando o histórico. Não apague esse diretório antes de desinstalar.

Se o conteúdo de um arquivo instalado foi modificado ou removido localmente, a desinstalação recusa sobrescrevê-lo, salvo se ele já corresponde ao estado original. Salve suas alterações e restaure o conteúdo da versão instalada (ou o original do backup) antes de repetir. Não há opção `--force` que descarte edições. Alterações apenas de permissões não são tratadas como alterações de conteúdo.

Para atualizar, use o desinstalador da versão atual e depois o instalador da nova versão. Não há atualização automática nem gerenciamento dos pacotes do driver.

## Desenvolvimento

```bash
./scripts/check.sh
```

Executa `bash -n`, ShellCheck quando disponível e testes `unittest` da biblioteca padrão do Python. O CI instala ShellCheck e o executa obrigatoriamente. Os testes alteram cópias dos scripts para apontar para arquivos temporários; os scripts de produção não aceitam variáveis de ambiente para redirecionar caminhos privilegiados.

A cobertura inclui sequência do marker/stop, pausa de 1,5 segundo com USB desautorizado, reautorização, ausência de start/restart no `post`, leitor ausente/duplicado, falha de parada/pausa, timeout do helper, instalação, backup, rollback, recusa de conflitos e restauração interrompida. A aprovação desses testes não substitui o roteiro físico acima.

Licença: [MIT](LICENSE), somente para os arquivos originais deste workaround. Nenhum código do driver foi incorporado. Os termos do driver continuam separados.
