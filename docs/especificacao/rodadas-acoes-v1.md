# Contrato v1 — rodadas, ações e orçamento

**Status:** especificação de contrato para o MVP; recomendações ainda precisam ser promovidas a decisões de produto antes de congelar uma competição.

**Escopo:** relógio de rodada, observações, propostas, validação, resolução de conflitos, orçamento, transições, atomicidade, falhas e reprodução. Este documento não define modelos econômicos nem tarifas de ação.

## 1. Vocabulário e autoridade

- **Experimento:** execução com snapshot, horizonte, cenário, políticas/agentes, modelos, regras e sementes congelados.
- **Instância:** cópia mutável e isolada do estado usada por um participante ou política de referência.
- **Rodada `r`:** um ano sintético. A rodada `1` parte do estado do ano sintético `0`.
- **Proposta:** conjunto serializado de ações submetido por uma política para uma instância e rodada.
- **Ação aceita:** ação autorizada pelo árbitro após validações, orçamento e conflitos.
- **Efeito pendente:** mudança aprovada e registrada que só se torna efetiva em uma rodada futura.
- **Commit da rodada:** publicação atômica do estado candidato e dos eventos/resultados autoritativos daquela rodada.

O estado é escrito apenas pelo orquestrador/árbitro. Agentes recebem observações somente de leitura e submetem propostas; não editam o snapshot, estado, arquivos ou simulador. O catálogo de ações, as tarifas e as regras versionadas no experimento são a autoridade. Custos ou pedidos de orçamento enviados pelo agente não autorizam nem alteram gastos.

## 2. Decisões existentes

Estas decisões estão registradas na configuração ou na arquitetura vigente:

| Tema | Decisão existente | Fonte |
|---|---|---|
| Relógio | Uma rodada equivale a um ano sintético; modelos anuais avançam uma vez por rodada. Mobilidade executa apenas janelas representativas configuradas e seus resultados não são anualizados sem hipótese e validação documentadas. | `configs/cities/aurora-base-v1.yaml`; `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` §§7, 16 |
| Horizonte | Padrão de 10 rodadas, configurado em `default_horizon_rounds`. | `configs/cities/aurora-base-v1.yaml` |
| Orçamento | 100 créditos simulados (CS) por rodada: 60 para operações fixas, 10 de reserva e 30 discricionários. CS é economia de jogo, sem conversão para BRL. | YAML `finance`; `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` §§3, 16 |
| Estado inicial | `aurora-base-v1` é canônico e imutável. Cada participante/referência recebe cópia independente; o estado desenvolvido por uma cópia não vaza para outra. O ID/hash inicial fica registrado. | YAML `arena`; `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` §9 |
| Condições comparadas | Cenários e aleatoriedade são comuns/pareados entre instâncias comparadas; versões e configuração do benchmark são congeladas. | YAML `arena`; arquiteturas §§9 |
| Observação e autoridade | O agente recebe observação documentada e propõe ações tipadas. O servidor calcula custos; não confia em custos fornecidos pelo agente. | `docs/conceito/urban-twin-arena.md` §6; `docs/arquitetura/arquitetura-completa-urban-twin-arena.md` §§5, 8 |
| Transação | Modelos produzem estado candidato. O estado só é confirmado se modelos e invariantes terminarem sem erro; eventos e estado confirmam juntos. | `docs/arquitetura/arquitetura-completa-urban-twin-arena.md` §§2, 3, 9 |
| Famílias de ação planejadas | Plano semafórico; frequência de ônibus; manutenção viária; faixa de ônibus ou ciclovia. Custos, limites e atrasos são categorias, não tarifas numéricas executáveis. | `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` §8 |
| Atrasos e recorrência | Infraestrutura consome orçamento na rodada de aprovação, entra em serviço após atraso configurado e pode gerar manutenção nas rodadas seguintes. | `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` §7; arquitetura completa §6 |

## 3. Recomendações para o MVP

As regras abaixo fecham o fluxo operacional sem presumir uma economia que não foi especificada. São recomendações de contrato, não fatos já codificados na configuração.

### 3.1 Observação

No início da rodada, cada instância recebe uma observação derivada exclusivamente do último estado comprometido daquela instância e das condições externas versionadas para a rodada. Todas as propostas dessa instância usam a mesma observação congelada; nenhuma proposta vê a ação ou o resultado de outra proposta da mesma rodada.

Contrato recomendado da observação:

```json
{
  "schema_version": "1.0",
  "experiment_id": "<id>",
  "instance_id": "<id>",
  "round": 1,
  "synthetic_year": 1,
  "parent_state_hash": "<hash do estado comprometido anterior>",
  "initial_snapshot_id": "aurora-base-v1:<hash>",
  "scenario_id": "<versão>.<id>",
  "visible_state": {},
  "available_actions": [],
  "budget_view": {},
  "pending_effects": [],
  "observation_policy_version": "<versão>"
}
```

`visible_state` contém apenas campos explicitamente liberados pelo protocolo. `available_actions`, `budget_view` e `pending_effects` devem refletir as regras e compromissos daquela cópia sem revelar dados privados de outros participantes. O orçamento mostrado deve distinguir limite discricionário, compromissos já contabilizados e saldo para novas ações; não deve sugerir que os 100 CS estão todos disponíveis ao agente.

### 3.2 Proposta e validação

Uma proposta identifica `proposal_id`, `experiment_id`, `instance_id`, rodada, agente/política, hash da observação respondida e uma chave de idempotência. Recomenda-se no máximo uma proposta por participante/instância/rodada; uma proposta vazia equivale a não agir. Ela contém zero ou mais ações tipadas. Cada ação declara ID estável dentro da proposta, tipo, alvo, parâmetros tipados e justificativa opcional. Unidades e schemas são definidos pelo catálogo versionado da ação. A proposta não pode incluir efeitos de estado calculados pelo próprio agente.

Validação recomendada, antes de qualquer efeito:

1. verificar versão/schema, identidade, rodada e hash da observação;
2. verificar limite de tamanho, prazo e quantidade máxima de ações do runtime;
3. verificar tipo permitido, autoridade, alvo existente, unidades, parâmetros, faixa, capacidade, pré-condições e restrições territoriais;
4. calcular custo pelo catálogo do servidor e verificar recursos/compromissos aplicáveis;
5. avaliar dependências e conflitos usando o mesmo estado pré-rodada;
6. devolver uma decisão explícita por ação e pela proposta, com regras verificadas, custo calculado, motivo e efeitos/atrasos previstos.

Proposta vazia é válida e equivale a não agir. Uma ação inválida é rejeitada com código e explicação estáveis. Recomenda-se tratar a proposta de um participante como pacote atômico: se uma ação depende de outra, ambas são aceitas ou rejeitadas juntas. Uma rejeição de proposta não invalida por si só a rodada nem propostas de outras instâncias isoladas. Repetir a mesma identidade e conteúdo devolve a decisão existente; reutilizar a identidade com conteúdo diferente resulta em conflito explícito.

O campo `budget_request` aparece no exemplo de `docs/conceito/urban-twin-arena.md`, mas conflita com o custo autoritativo calculado pelo servidor. No v1, recomenda-se removê-lo do contrato normativo ou aceitá-lo apenas como anotação sem efeito; nunca usá-lo como preço ou permissão.

### 3.3 Simultaneidade e conflitos

Recomenda-se simultaneidade por rodada dentro de cada instância: todas as decisões são produzidas sobre a observação congelada, e só depois o árbitro valida e resolve o lote. Instâncias de agentes diferentes têm estados, orçamentos e alvos isolados; portanto, não existe conflito material entre ações de participantes em cópias diferentes. Ações de uma mesma proposta podem conflitar entre si ao tocar o mesmo recurso, capacidade, ativo ou intervalo temporal.

O árbitro deve usar uma chave de conflito explícita no catálogo (recurso/alvo e intervalo afetado), construir o grafo de conflitos antes de aplicar ações e registrar os grupos conflitantes. Não resolver conflito pela ordem incidental de chegada de chamadas ou escrita no banco.

**Política sugerida para o MVP:** rejeitar o pacote inteiro quando suas ações forem internamente conflitantes. Se houver mais de uma proposta autorizada sobre a mesma instância no futuro, congelar previamente uma política determinística e versionada; não conceder precedência silenciosa ao primeiro pedido. A escolha entre rejeitar todos os envolvidos, prioridade rotativa ou outro desempate permanece aberta na seção 4.

### 3.4 Orçamento e custos

O envelope configurado é 100 CS por rodada; a parcela discricionária configurada é 30 CS. Recomenda-se que o MVP permita novas ações apenas contra a parcela discricionária, mantenha os 60 CS de operações fixas fora da autorização de ações e não permita uso automático dos 10 CS de reserva. Esta interpretação preserva a alocação documentada sem inventar receitas, dívida ou fórmula de caixa.

Cada entrada do catálogo de ação deve declarar, quando aplicável:

- custo pontual e rodada em que é comprometido/realizado;
- custo recorrente, sua unidade temporal, início e fim;
- custo de operação/manutenção e a regra de encerramento;
- atraso e rodada de efetivação;
- regra de arredondamento/unidade e versão da tarifa;
- recursos/capacidades consumidos enquanto a ação está pendente ou ativa.

O agente não escolhe tarifas. O árbitro devolve o detalhamento calculado. O registro diferencia **aprovado/comprometido**, **cobrado no orçamento da rodada** e **efeito efetivado**; esses eventos podem ocorrer em rodadas distintas. Para obras, o custo de aprovação na rodada corrente, atraso até entrada em serviço e manutenção posterior são compatíveis com o que já está documentado, mas seus valores e datas concretas dependem do catálogo.

Até existir política financeira, recomenda-se não carregar saldo discricionário não gasto para outras rodadas e não permitir que ação dependa de receita futura não modelada. Uma ação com custo recorrente só pode ser aceita quando o catálogo permitir calcular a obrigação e a regra de orçamento declarada no experimento conseguir verificá-la. Se não houver tarifa/regra completa, a ação fica indisponível, em vez de receber custo zero ou estimado. Esta recomendação não fixa como compromissos futuros consomem os 30 CS.

### 3.5 Ordem de transições

Ordem operacional recomendada; cada etapa usa a versão de regra/modelo congelada no manifesto:

1. carregar o último estado comprometido e materializar o cenário exógeno comum/pareado da rodada;
2. processar efeitos pendentes cujo marco de efetivação seja esta rodada, em estado candidato;
3. gerar e congelar observações a partir do estado definido pelo protocolo; a política recomendada é observar efeitos vencidos e ainda não observar ações novas da própria rodada;
4. coletar propostas até o limite configurado; fechar o lote sem aplicar efeitos;
5. validar schemas, alvos, pré-condições, custos, orçamento e conflitos;
6. registrar decisões e construir o estado candidato: compromissos são lançados no marco financeiro definido; ações imediatas entram na transição corrente; ações atrasadas são agendadas com rodada efetiva explícita;
7. executar modelos na ordem de dependência declarada (mobilidade apenas nas janelas configuradas; cada modelo anual no máximo uma vez por rodada);
8. validar invariantes e balanços implementados, calcular métricas, deltas e hashes;
9. persistir estado, decisões, eventos e resultados em um único commit lógico.

A política de observação em relação a efeitos pendentes precisa ser congelada para eliminar ambiguidade de “antes/depois”: nesta recomendação, uma obra que vence no início da rodada já aparece como ativa na observação; novas propostas não produzem efeito visível até a próxima observação, salvo ação cujo catálogo declare efeito imediato na transição corrente. Uma janela representativa de mobilidade não representa um ano de tráfego.

### 3.6 Atomicidade, falhas e repetição

A execução trabalha em candidato isolado e publica estado, lançamentos e eventos de domínio somente no commit final. O commit exige que o hash do estado pai ainda corresponda ao hash lido pela rodada; isso impede dois workers de confirmar a mesma transição. Antes desse commit, falha, cancelamento ou violação de invariante deixa intacto o último estado e orçamento comprometidos. Artefatos temporários podem ser preservados para diagnóstico, mas ficam marcados como parciais/não publicados e não são consumidos como resultado concluído.

O log durável de tentativas (propostas recebidas, decisões de validação e diagnóstico de falha) é separado dos eventos científicos da rodada. Ele sobrevive a rollback/cancelamento. Estado, lançamentos, métricas publicadas e eventos de domínio pertencem ao commit atômico; uma rodada falha não deixa nenhum deles parcialmente visível.

Distinções recomendadas:

- **Rejeição de ação/proposta:** decisão normal do árbitro; registrada, sem alterar estado por si só. Outras ações compatíveis podem prosseguir conforme a política de atomicidade da proposta.
- **Falha da rodada:** erro do runtime/modelo, timeout global, saída inválida, invariantes violados, artefato obrigatório ausente/corrompido ou falha de persistência. Nenhuma parte do estado candidato é confirmada.
- **Cancelamento:** cooperativo e idempotente; antes do commit cancela toda a rodada sem efeito parcial; após o commit só pode encerrar antes da próxima rodada.
- **Retry:** somente com chave idempotente de experimento/instância/rodada/proposta e o mesmo manifesto. O commit deve usar compare-and-swap pelo hash pai. Uma repetição igual retorna a decisão/resultado existente; mesma identidade com conteúdo diferente falha como conflito; concorrência entre workers permite no máximo um commit. Um retry não pode cobrar duas vezes nem aplicar duas vezes ação ou evento. Falhas determinísticas não devem ser repetidas indefinidamente; classificação, limite e backoff são parte da política operacional do executor.

A decisão sobre uma proposta rejeitada, inclusive motivo e custo estimado, permanece auditável mesmo quando a rodada falha. O status de rodada deve distinguir ao menos `pending`, `running`, `committed`, `failed` e `cancelled`; falha não é um resultado científico com métricas finais.

### 3.7 Registro e reprodução

O registro é append-only para decisões e eventos da execução. Por rodada, preservar pelo menos:

- IDs do experimento, instância, rodada e participante; hash do estado pai e do estado confirmado;
- snapshot inicial `aurora-base-v1`, hash/configuração, cenário e dados de entrada;
- observação exata entregue e sua política/schema;
- payload original da proposta, identidade/versão do agente e resultado bruto do runtime;
- ações normalizadas, validações, rejeições, conflitos/desempates e versões de regras;
- tarifas/cálculos, custos comprometidos e realizados, orçamento visível e compromissos pendentes;
- efeitos imediatos/agendados, rodada efetiva e delta de estado;
- versões de modelos, parâmetros, imagens/ambiente relevantes, sementes por subsistema e artefatos com checksums;
- saídas, diagnósticos, invariantes, métricas, cursor/ID de eventos e status de publicação.

Reproduzir uma execução significa iniciar do hash do snapshot e manifesto congelados, reaplicar a sequência registrada de observações/propostas/decisões e executar modelos com versões, entradas e sementes compatíveis. Comparar hashes e resultados segundo tolerância declarada para cada modelo; igualdade bit a bit só pode ser exigida quando o modelo e o ambiente oferecerem esse contrato. Se faltarem entrada, artefato, versão ou semente, marcar a reprodução como incompleta e identificar o elo ausente. Uma repetição de uma política estocástica também deve registrar a proposta originalmente emitida; chamar novamente o agente não garante a mesma proposta.

## 4. Decisões ainda abertas

Estas questões precisam de decisão antes de declarar o contrato financeiro e competitivo totalmente congelado:

1. **Conflitos:** política de desempate quando houver múltiplas propostas para o mesmo recurso; a arquitetura exige prioridade determinística predefinida, mas não a define.
2. **Orçamento:** se reserva pode ser usada e por quem; saldo discricionário acumula ou expira; tratamento de receitas, dívida, arredondamento e compromissos recorrentes futuros; se recorrências reduzem a verba discricionária do ano de cobrança.
3. **Catálogo:** tarifas, limites, unidades e atrasos efetivos para cada ação, e quais quatro famílias estão realmente ativadas em cada release.
4. **Dependências:** atomicidade de propostas com ações relacionadas, limites de ações por rodada e comportamento para rejeições parciais.
5. **Tempo:** para cada ação, se o primeiro efeito ocorre na rodada de aprovação ou na seguinte, como atrasos zero/um são contados e em que momento custos recorrentes começam/terminam.
6. **Execução:** prazos de proposta/modelo, política de retry/backoff e cancelamento quando um modelo não pode ser interrompido imediatamente.
7. **Reprodução:** tolerâncias de comparação por modelo e quais componentes têm determinismo bit a bit garantido.
8. **Observação:** campos exatos liberados por agente, métricas atrasadas e se resultados de rodadas passadas podem ser consultados durante a competição.

Até esses pontos serem resolvidos, o MVP deve expor somente ações cujo schema, autorização, tarifa, conflito e cronograma estejam inteiramente definidos. Não usar uma fórmula genérica, custo zero ou média inferida para preencher lacunas.

## 5. Divergências documentais identificadas

- `docs/conceito/urban-twin-arena.md` §4 trata a duração da rodada como algo ainda a declarar e §13 a lista como pergunta aberta. Isso diverge de `configs/cities/aurora-base-v1.yaml` (`one_synthetic_year`) e de `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` §§7 e 16, que fixam um ano sintético. Para esta especificação, prevalecem a configuração e a arquitetura específica de Aurora.
- O horizonte padrão de 10 rodadas está no YAML, mas a arquitetura de cidade sintética só exige o mesmo horizonte entre instâncias e não transcreve o valor padrão.
- `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` §8 exige aplicação atômica, enquanto a arquitetura completa descreve estado candidato e commit condicionado a modelos/invariantes. Esta especificação interpreta atomicidade como publicação indivisível da rodada; rejeições normais de proposta são decisões auditáveis, e falha de processamento aborta o commit.
- A arquitetura de cidade sintética §8 mostra `budget_request` no exemplo conceitual do agente, mas a arquitetura completa §§5/8 diz que custo do agente é ignorado e calculado pelo servidor. O campo não deve ser fonte de autoridade.
- A arquitetura de cidade sintética §13 coloca ações e orçamento no MVP 2, enquanto `docs/arquitetura/arquitetura-completa-urban-twin-arena.md` no roadmap coloca a fatia de ações mais adiante (MVP 4). Os prompts de execução também têm escopos próprios. A fase vigente deve ser confirmada no roadmap; este documento especifica o contrato, não altera a sequência de entrega.
- A arquitetura completa §9 determina prioridade determinística para conflitos, sem indicar regra. O YAML e os documentos não contêm tarifas numéricas nem fórmulas por ação, regra de saldo, uso da reserva ou contabilização completa de recorrências.

## 6. Critérios verificáveis para o MVP

Estes critérios definem evidência de implementação; valores numéricos em fixtures de teste são artificiais e não definem tarifas de Aurora.

- **Identidade/idempotência:** submissão repetida com mesma identidade e conteúdo retorna a mesma decisão; conteúdo diferente com a mesma identidade é conflito. Duas execuções concorrentes para o mesmo hash pai produzem no máximo um commit; a outra detecta estado pai obsoleto.
- **Orçamento:** com uma tarifa versionada e orçamento disponível `B`, custo igual a `B` respeita o limite, custo acima de `B` é rejeitado e tarifa ausente deixa a ação indisponível. Repetir a rodada não cobra novamente. Casos para compromissos recorrentes só são executáveis quando uma regra financeira versionada estiver definida; não se codifica fórmula implícita.
- **Conflitos:** testar ao menos duas ações compatíveis e um par que compartilhe chave de conflito/recurso/intervalo. A decisão segue a política congelada, é independente da ordem de chegada e registra os IDs e motivos. Propostas de instâncias isoladas não entram no mesmo conjunto de conflito.
- **Atrasos:** para cada ação habilitada, declarar rodada de aprovação, rodada efetiva e início/fim de custos recorrentes. Testar efeito imediato, atraso configurado e ação ainda pendente; a observação inclui efeitos vencidos e exclui efeitos futuros.
- **Atomicidade/falha:** injetar falha após validação, cálculo de custo, aplicação candidata, saída de modelo, validação de invariantes e durante a persistência. Em cada ponto, estado/orçamento/eventos científicos permanecem no último commit; tentativa, decisões e diagnóstico continuam no log durável; artefatos incompletos não são publicados.
- **Reprodução:** executar novamente a partir do mesmo manifesto e das propostas gravadas; verificar hashes/deltas conforme tolerância declarada. Ausência de semente, versão ou artefato produz estado de reprodução incompleta, em vez de alegar igualdade.

Uma versão de MVP pode ser considerada implementável quando cada ação habilitada tiver schema/unidades, alvos e permissões, pré-condições, tarifa calculável, custos pontuais/recorrentes, atraso e conflitos definidos; e a configuração do experimento congelar horizonte, observação, política de orçamento, ordem, regras, versões, sementes e política de idempotência. Esses critérios não afirmam validade econômica ou empírica de Aurora.
