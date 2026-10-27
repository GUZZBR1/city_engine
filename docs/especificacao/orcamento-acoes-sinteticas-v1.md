# Catálogo mínimo de ações e orçamento — hipótese sintética v1

**Status:** proposta de configuração para o primeiro protótipo anual; não implementada e não calibrada.

**Resolução integrada:** o teto sem saldo acumulado, reserva expirada, compromisso de custos futuros dentro dos 30 CS e ações habilitadas/desabilitadas estão congelados em `contrato-evolucao-urbana-v1.md`. Este arquivo mantém as tarifas e regras de domínio detalhadas; nenhuma ação é considerada executável antes da integração ao runtime.

**Escopo:** definir poucas ações, tarifas exemplificativas, pré-condições, limites, atrasos e uma regra reproduzível para o envelope atual de Aurora. Todos os valores monetários abaixo são créditos simulados (CS), nunca BRL. Este documento não altera o YAML nem afirma que as ações já são executáveis.

## 1. Base existente e limite de implementação

O YAML `configs/cities/aurora-base-v1.yaml` fixa 100 CS por rodada/ano sintético: 60 para operações fixas, 10 de reserva e 30 discricionários. A moeda está declarada como `simulated_urban_credits`, sem conversão para reais. O modelo de configuração valida que as três parcelas fecham com o total; não define catálogo, tarifas, saldo entre rodadas ou custo recorrente.

Os contratos de rodadas recomendam custo calculado pelo árbitro a partir de catálogo versionado, validação antes de aplicar efeitos, e publicação atômica de estado/eventos. A arquitetura lista ajuste semafórico, frequência de ônibus, manutenção viária e faixa de ônibus/ciclovia como famílias planejadas, sem preço ou regra completa. Habitação, zoneamento, escola e saúde dependem dos respectivos modelos.

A referência integrada `feature-aurora-round-engine` registra somente um ciclo protocolar sem ação: valida o envelope e gasto zero, preserva o estado da cidade e marca a transição de domínio como não executada. No contrato-alvo esse modo se chama `protocol_noop`; `no_action` passa a designar uma rodada urbana anual sem ações, com modelos de referência habilitados. A implementação atual não executa ações, caixa, saldo, compromissos ou transições anuais. A mobilidade aceita planos semafóricos em janelas representativas; não anualiza esses resultados. A rota de ônibus do YAML é declarativa e não entra hoje na entrada do simulador.

Assim, os valores e políticas a seguir são **escolhas propostas** para uma configuração sintética versionada. Campos de estado ainda ausentes precisam ser adicionados e validados antes de habilitar a ação correspondente. Ausência de dado/modelo significa “indisponível”, nunca custo zero ou efeito presumido.

## 2. Regras propostas para o envelope

| Parcela por rodada | CS | Regra proposta |
|---|---:|---|
| Operações fixas | 60 | Fora da autorização de ações. Não pode ser realocada pelo agente. |
| Reserva | 10 | Indisponível para ações ordinárias; parcela não usada expira ao fechar a rodada. |
| Discricionário | 30 | Teto de custos das ações da rodada, incluindo parcelas pontuais e recorrências vencidas. |
| **Total** | **100** | Mantido em todas as rodadas, sem conversão para BRL. |

**Escolha proposta — sem saldo acumulado:** o limite discricionário reinicia em 30 CS a cada rodada. CS discricionário não usado não aumenta o limite de anos seguintes. Não há caixa, receita, dívida, juros ou saldo acumulado neste protótipo.

**Escolha proposta — compromissos recorrentes:** ao aprovar uma ação com cobrança futura conhecida, reservar a parcela correspondente dentro dos 30 CS da rodada em que vencerá. Para cada rodada `r`, a soma de custos pontuais cobrados em `r` e parcelas recorrentes comprometidas/vencidas em `r` não pode exceder 30. O compromisso reduz o espaço de novas ações daquela rodada, mas não representa dinheiro guardado. A aprovação só é aceita se couber em todas as rodadas afetadas até o término declarado do experimento. Não se presume financiamento depois do horizonte.

O saldo projetado depois de validar o lote da rodada é:

```text
disponível(r) = 30 - recorrências já comprometidas e vencendo em r
                - custos pontuais das novas ações aprovadas em r
                - novas recorrências comprometidas para r
```

O resultado deve ser não negativo. Para avaliar uma proposta antes de aprová-la, comparar seus custos com `30 - recorrências já comprometidas e vencendo em r`; somar custos pontuais e novas parcelas recorrentes do lote ao testar essa disponibilidade. A implementação deve também validar separadamente `60 + 10 + 30 = 100`, gasto da rodada `≤ 30` e compromissos futuros `≤ 30` em cada ano afetado. O agente não informa nem escolhe custo: eventual `budget_request` é apenas anotação; a tarifa vem do catálogo congelado no experimento.

## 3. Catálogo mínimo proposto

Tarifas, limites e atrasos da tabela são **configuração sintética de exemplo**. Cada versão ativa deve declarar IDs, unidades, tarifa, duração, rodada de cobrança/efeito, recursos de conflito e limites. CS são inteiros; não há arredondamento. `r` é a rodada de aprovação e equivale ao ano sintético de mesmo índice.

| ID / efeito observável | Custo proposto | Atraso e duração | Pré-condições e limite por proposta/rodada |
|---|---|---|---|
| `signal_timing_change` — substituir plano de um nó semafórico existente; verificar os parâmetros na entrada da janela SUMO e comparar métricas dessa janela pareada. | 2 CS pontuais na aprovação + 1 CS de operação na rodada aplicada. A intervenção dura uma rodada; renová-la exige nova ação. | Efeito na próxima janela de mobilidade executada na mesma rodada, depois do aceite. A tarifa total de 3 CS é cobrada na rodada de aplicação. Não atribuir efeito anual/populacional ao resultado da janela. | `node_id` deve existir; fases NS/EW e todos-vermelhos, durações positivas e ciclo dentro da faixa permitida; manter a soma do ciclo declarada. Máx. 1 alteração por nó e 2 nós por proposta/rodada. Duas alterações no mesmo nó conflitam. |
| `housing_add_units` — adicionar um pacote de 10 unidades à capacidade habitacional do distrito; verificar a diferença no estoque/capacidade. | 8 CS pontuais por pacote; sem recorrência neste protótipo porque custos de operação/manutenção habitacional não estão definidos. | Capacidade entra no início de `r+1`; custo é cobrado em `r`. Unidades permanecem no estoque após ativação. Não converte unidades em residentes ou domicílios ocupados. | Alvo deve ser distrito urbano com capacidade residencial edificável declarada no estado/configuração versionada; rejeitar área protegida e limite excedido. Máx. 2 pacotes por rodada no total e por distrito. **Indisponível até existir inventário/capacidade habitacional validável.** |
| `service_capacity_contract` — contratar +10 unidades de capacidade de serviço configurado (por exemplo, vagas/atendimentos, sempre com unidade do domínio); verificar capacidade ativa no estado do serviço. | 6 CS pontuais de preparação em `r` + 2 CS recorrentes em `r+1`, ano de serviço. A contratação dura só esse ano; renovação requer nova decisão/custo. | Serviço efetivo em `r+1`; o incremento temporário termina ao fim dessa rodada. O custo recorrente de 2 CS é reservado no teto de `r+1` na aprovação e cobrado quando o serviço entra em vigor. | Tipo, unidade, instalação e capacidade-base devem estar cadastrados; respeitar limite configurado por instalação. Máx. 1 contrato por instalação e 2 contratos por rodada. **Indisponível até existir inventário e modelo de capacidade/atendimento.** |

Os três efeitos têm limites verificáveis: plano de sinal no input/resultado da simulação da janela, estoque de unidades no estado habitacional futuro, e capacidade anual no estado de serviços futuro. Apenas o primeiro se apoia em dados de alvo já configurados. Mesmo para ele, custo e integração ao ciclo anual são propostas, e métricas de janela continuam sendo métricas de janela. As outras duas ações são especificações de extensão, não ações disponíveis hoje.

### 3.1 Restrições de domínio

- Construção habitacional altera capacidade/unidades, não população. Ocupação, migração, desocupação e residentes por distrito ficam inalterados até haver uma regra demográfica versionada e seus fluxos de entrada/saída fecharem.
- Capacidade de serviço não equivale a cobertura, qualidade, uso, população atendida ou redução de demanda não atendida. Só pode publicar o delta da capacidade definida e unidade correspondente enquanto o modelo de serviços não calcular indicadores adicionais.
- Ajuste semafórico não modifica automaticamente demanda, modo de viagem ou população. Executar as mesmas janelas, cenário e semente nas comparações; não extrapolar para o ano.
- Alvos não configurados, efeito sem métrica, tarifa incompleta ou duração recorrente indefinida tornam a ação indisponível.

## 4. Validação, simultaneidade e atomicidade

**Escolha proposta:** uma proposta por instância/rodada, avaliada contra a mesma observação e estado pai. Antes de qualquer mudança, o árbitro valida schema e unidades, alvo, faixa, pré-condições, limites, conflito, tarifa, orçamento corrente e todos os compromissos futuros. Custos são recalculados pelo servidor.

Para o primeiro protótipo, a proposta é um pacote atômico: se qualquer ação for inválida, exceder teto ou conflitar com outra ação no próprio pacote, rejeitar a proposta inteira. Não há aceitação parcial nem ordem de chegada como desempate. O estado candidato recebe todos os efeitos aprovados; estado, custos cobrados, compromissos e eventos autoritativos são confirmados num único commit. Falha posterior de modelo, invariantes ou persistência deixa intactos o último estado e orçamento comprometidos. Rejeição é uma decisão registrada e não uma falha de rodada.

Ações com conflito compartilham a chave `(tipo_de_recurso, alvo, intervalo_efetivo)`. Exemplos: duas alterações para o mesmo `node_id` na mesma rodada; dois pacotes de habitação acima da capacidade edificável do mesmo distrito; dois contratos na mesma instalação e período além do limite. Uma falha ou retry não pode cobrar nem aplicar duas vezes a mesma identidade de proposta/ação. A ordem do lote e a repetição idêntica não alteram custos ou resultado.

Registro por ação deve distinguir: proposta original; decisão e motivo; versão de catálogo; custo pontual cobrado; recorrência devida e compromisso futuro; alvo; rodada de aprovação/efetivação/fim; delta validado; proveniência `synthetic_config` ou `simulated`; e resultado do commit. Custos informados pelo agente nunca são autoridade.

## 5. Exemplos numéricos — configuração sintética

Os valores desta seção demonstram a regra e **não são tarifas de Aurora implementadas, estimativas de custo real ou referências em BRL**.

### Exemplo A — pacote habitacional e ajuste semafórico

Em `r=1`, uma proposta solicita dois pacotes habitacionais em um distrito elegível e uma alteração de um nó:

```text
habitação: 2 × 8 = 16 CS pontuais em r=1; +20 unidades entram em r=2
semáforo: 2 CS pontuais + 1 CS de operação = 3 CS em r=1
gasto discricionário r=1: 16 + 3 = 19 CS; limite = 30; restante = 11 CS
```

O resultado de população permanece inalterado. Se o distrito só tiver capacidade para um pacote, rejeitar a proposta inteira e registrar a pré-condição violada; não cobrar 8 CS parcialmente.

### Exemplo B — contrato de serviço e orçamento futuro

Em `r=1`, um contrato de serviço custa 6 CS de preparação e reserva 2 CS do limite discricionário de `r=2`:

```text
r=1: 6 CS cobrados; ficam 24 CS para outras ações
r=2: 2 CS recorrentes cobrados; ficam no máximo 28 CS para novas ações
efeito: +10 unidades de capacidade durante r=2; termina no fecho de r=2
```

Se outra ação já comprometeu 29 CS de `r=2`, rejeitar o novo contrato na aprovação em `r=1`, mesmo que seus 6 CS de preparação caibam em `r=1`. Se `r=2` estiver fora do horizonte congelado, o contrato é indisponível. A reserva futura consome teto discricionário daquele ano; não cria saldo ou fonte financeira.

### Exemplo C — teto corrente e pacote atômico

Suponha em `r=3` dois pacotes habitacionais (16 CS), um ajuste semafórico (3 CS) e dois preparos de serviço (12 CS), que totalizam 31 CS em `r=3`. Rejeitar a proposta inteira por exceder 30; gasto, estado, ativações e compromissos permanecem inalterados. Uma proposta com custo total de exatamente 30 CS é elegível se todas as demais validações e compromissos futuros também passarem.

## 6. Critérios testáveis

Todos os casos devem usar fixtures sintéticas e configuração/catalogo versionados. A implementação só pode afirmar suporte às ações que passarem critérios aplicáveis.

1. **Envelope:** validar `60 + 10 + 30 = 100`; rejeitar qualquer configuração cujo total ou soma de parcelas divirja. Nenhuma proposta pode debitar operações fixas ou reserva.
2. **Expiração do não gasto:** gastar 12 dos 30 CS em `r` deixa 18 indisponíveis após o fecho; em `r+1` o limite volta a 30 antes de compromissos, não a 48. Os 10 CS da reserva não reaparecem como ação ordinária.
3. **Limite:** custos discricionários de 30 CS podem ser aceitos; 31 CS são rejeitados sem gasto/efeito parcial. Testar também parcela recorrente de 2 CS mais 29 CS de novas ações = rejeição.
4. **Recorrência e horizonte:** contrato de serviço aprovado em `r` cobra setup uma vez, reserva e cobra a parcela em `r+1` exatamente uma vez, encerra ao final de `r+1` e não cobra em `r+2`. Repetir a proposta idêntica não duplica cobrança. Ação cujo compromisso ultrapasse o teto de qualquer ano futuro ou o horizonte é rejeitada.
5. **Atrasos:** habitação aprovada em `r` fica pendente durante `r`, ativa somente em `r+1`; serviço também só ativa em `r+1` e expira no fecho; plano semafórico aprovado antes da execução é aplicado na janela declarada da rodada. Observações distinguem pendente, ativo e encerrado.
6. **Pré-condições e limites:** testar alvo ausente, área protegida, capacidade insuficiente, faixa inválida, limite por alvo e limite global. Cada rejeição inclui código/motivo estável e mantém estado e orçamento.
7. **Conflito/atomicidade:** duas ações para o mesmo recurso efetivo são detectadas independentemente da ordem da lista. Uma proposta com um item inválido ou conflito não aplica/cobra itens válidos do mesmo pacote. Falha do modelo ou commit depois da validação preserva estado, custo e eventos autoritativos da rodada anterior.
8. **Idempotência:** repetir a mesma identidade e conteúdo retorna a decisão/resultado anterior sem segundo débito; mesma identidade com conteúdo diferente é conflito.
9. **Efeitos e balanços:** unidades habitacionais acrescentadas respeitam limite por distrito e não alteram população por si só; serviço publica apenas capacidade/unidade contratada no período; semáforo muda apenas o plano e as métricas da janela configurada. Mobilidade não é multiplicada/anualizada.
10. **Proveniência:** cada parâmetro deste catálogo e cada efeito construído com ele permanece marcado como sintético/simulado, sem classificação de observação real.

## 7. Escolhas abertas antes de congelar o contrato

- O protótipo deve implementar primeiro a ação semafórica já compatível com alvos configurados, ou ampliar estado/modelos para habitação e serviços antes de ativar qualquer ação urbana anual?
- Quais unidades, instalações, distritos edificáveis e capacidades máximas vão integrar os novos inventários? O estado atual não define estoque habitacional espacial, área edificável nem inventário de serviços.
- A recorrência futura deve ser comprometida no momento da aprovação, como proposto, ou decidida/renovada anualmente? Se houver renovação discricionária, que regra governa continuidade e expiração?
- Qual ação pode solicitar a reserva de 10 CS, sob que autoridade, condição, teto e regra de registro? A proposta v1 mantém a parcela inacessível.
- Quais tarifas sintéticas, intervalos máximos, faixas de parâmetros, duração, desempate de conflito e regras de manutenção serão congelados por versão do experimento?
- Quando existirem modelos de ocupação, demografia e serviço, quais relações causais e grupos serão modelados? Até lá não derivar residentes, acesso ou qualidade de vida de capacidade instalada.
- Como modelar efeitos externos anuais comuns às políticas? Nenhuma receita, dívida ou crescimento populacional é introduzido por esta proposta.

## 8. Referências internas consultadas

- `configs/cities/aurora-base-v1.yaml`, seções `population`, `districts`, `mobility`, `finance` e `arena`.
- `packages/urban_arena/urban_arena/models.py` e `packages/urban_arena/urban_arena/city.py`: configuração/snapshot e balanços atualmente validados.
- `docs/conceito/urban-twin-arena.md`, §§4 e 6: ciclo e contrato conceitual de ação.
- `docs/arquitetura/cidade-sintetica-urban-twin-arena.md`, §§7–8: relógio anual, atraso/manutenção e famílias de ação previstas.
- `rodadas-acoes-v1.md`, §§3–4 e 6: validação, orçamento, atomicidade e critérios.
- `estado-cidade-v1.md`, §§1, 3–4: campos e domínios ausentes.
- `contrato-integrado-arena-v1.md`, §§1–3: limites da fatia protocolar legada.
- `contrato-evolucao-urbana-v1.md`: resoluções normativas da integração v1.
- `packages/urban_arena/urban_arena/rounds.py`: implementação de referência lida sem edição; só envelope e recibo protocolar sem transição.
