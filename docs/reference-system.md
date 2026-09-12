# Inspeção do sistema de referência

**Português** | [English](reference-system.en.md) · [README](../README.md)

Inspeção somente leitura realizada durante a preparação do projeto. Estes dados descrevem a configuração encontrada; não certificam a execução dos scripts novos nesse hardware.

| Item | Observado |
| --- | --- |
| Distribuição | Zorin OS 18.1 |
| Kernel em execução | `7.0.0-31-generic` |
| systemd | `255.4-1ubuntu8.17` |
| Modo de suspensão | `[s2idle] deep` (s2idle selecionado) |
| Leitor | `1c7a:0576`, caminho USB `3-8` naquele momento |
| USB | `authorized=1`, `power/control=on`, `power/runtime_status=active` |
| Regra local | `/etc/udev/rules.d/60-egis0576-fp-nosuspend.rules` força `power/control=on` no evento add desse VID/PID |
| Serviço | `Type=dbus`, `BusName=net.reactivated.Fprint` |
| Drop-in | `10-egis0576-resume.conf` adiciona o helper em `ExecStartPre` |
| Marker | Ausente no momento da inspeção |

As linhas de comando do kernel e do GRUB examinadas não continham `mem_sleep_default=deep`. Isso não identifica a origem histórica da seleção de s2idle nem garante o modo que será selecionado em outro boot. O instalador verifica o modo ativo e não edita o GRUB.

## Commit do driver usado na validação

O usuário informou que a validação original utilizou o commit [7849db90c37131b0662e7e17059caebfb9b277c7](https://github.com/PHILIPPDEV5396/libfprint-egis0576/commit/7849db90c37131b0662e7e17059caebfb9b277c7) do projeto `PHILIPPDEV5396/libfprint-egis0576`. Essa informação foi fornecida pelo usuário, não extraída do binário durante a inspeção. O workaround não baixa, altera ou fixa automaticamente essa versão do driver.

## Diferenças entre o código encontrado e o empacotamento

O hook instalado cria um marker vazio, para o fprintd, desautoriza o USB, espera 1,5 segundo, reautoriza e remove o marker. Não reinicia o daemon no `post`. Usa `set +e`, executa por fase `pre/post` sem filtrar o segundo argumento e remove o marker mesmo se não encontrar o leitor. Contém logs de depuração.

O helper instalado faz 150 esperas de 0,1 segundo e então retorna sucesso **mesmo que o marker persista**. O helper novo faz até 120 esperas de 0,25 segundo e retorna falha se a recuperação continuar pendente. Essa mudança de política, a filtragem para `suspend` e as proteções de erro precisam ser incluídas na validação física da nova versão. O empacotamento não é uma cópia byte a byte da configuração em uso.

Há três arquivos adicionais, todos com modo `0755`, no mesmo diretório do hook:

- `50-egis0576-fp-resume.sh.bak`
- `50-egis0576-fp-resume.sh.before-sync`
- `50-egis0576-fp-resume.sh.debug`

Eles contêm versões alternativas da recuperação do leitor. Não se deve presumir que uma extensão de backup desativa um executável nessa pasta. O instalador os trata conservadoramente como possíveis conflitos e exige revisão. Para instalar a nova versão, mantenha as cópias preservadas fora dos diretórios de hooks; o projeto não as move automaticamente. A inspeção não comprovou quais dessas cópias foram executadas em suspensões anteriores.

## Autosuspend USB é uma configuração separada

`s2idle` é o modo de suspensão do sistema; `power/control=on` desativa autosuspend em tempo ocioso para esse USB. São configurações distintas. O projeto não instala nem remove a regra udev encontrada. Um ambiente com `power/control=auto` difere do sistema de referência e deve ser investigado como tal. Os comentários de uma regra antiga não comprovam a versão ou o protocolo do driver atualmente carregado.

Nenhum arquivo de sistema foi modificado, nenhum serviço foi reiniciado e nenhuma suspensão ou autenticação foi disparada durante a inspeção.
