# Agentes e escopo executável da Arena — v1

**Status:** contrato normativo do benchmark inicial; fases futuras condicionais.
**Escopo do MVP de comparação:** Aurora sintética, baseline e cinco políticas determinísticas de temporização, uma intervenção em um cruzamento por janela, mesma entrada e seed; sem aprendizado, score universal, orçamento urbano, obras ou alegações anuais.
**Evidência de implementação:** consultar [comparação SUMO](../../apps/api/app/arena_mobility.py), [criação da Arena](../../apps/api/app/arena_jobs.py), [políticas](../../packages/urban_arena/urban_arena/policies.py), [árbitro](../../packages/urban_arena/urban_arena/actions.py), [motor de rodadas](../../packages/urban_arena/urban_arena/round_engine.py) e [README do pacote](../../packages/urban_arena/README.md).

## 1. Entidades e autoridade

- **Participante ou empresa** é a organização responsável por submeter uma entrada, quando submissão externa existir. Uma empresa não ganha autoridade sobre dados, regras, simulador, orçamento ou avaliação por participar. O runtime atual não modela organizações nem recebe código externo.
- **Política competidora** é a unidade comparada: função versionada que recebe uma observação congelada e devolve uma proposta. No MVP atual, as políticas são implementações internas e determinísticas de temporização semafórica; não são modelos treinados nem agentes autônomos gerais. Uma política avaliada não equivale a uma empresa.
- **Políticas do produto** são regras públicas e iguais para todos: entrada permitida, ações habilitadas, limites, semântica de falha, janela e procedimento de comparação. Mudança nelas exige versão nova do experimento.
- **Runtime** cria cópias isoladas, congela as observações, chama as políticas, registra as propostas e executa somente o resultado autorizado. Ele controla relógios, limites e persistência.
- **Árbitro** é a validação determinística no servidor. Ele verifica identidade contextual, hash observado, alvo, parâmetros e conflitos; calcula custos quando houver tarifa aplicável; aceita ou rejeita a proposta atomicamente. A identidade/versão da política é vinculada pelo runtime ao `ProposalRecord` e deve ser congelada no manifesto; `ActionProposal` hoje não carrega esses dois campos. A política não arbitra a própria proposta.
- **Subagentes de engenharia** (por exemplo, `architect`, `critic` e `verifier`) são colaboradores usados para construir ou revisar o software. Não são participantes, não recebem cópias da cidade e não executam durante partidas.

## 2. Contrato honesto do MVP

O benchmark inicial fica restrito a:

1. Aurora gerada/configurada sinteticamente, com proveniência `synthetic`; a rede, demanda, semáforos e valores são pressupostos reproduzíveis, não medições de uma cidade real.
2. Um baseline sem intervenção e cinco políticas determinísticas de temporização, todas identificadas por `policy_id` e versão congelada. A regra e os tempos de cada política devem estar publicados antes da execução.
3. Uma única ação de temporização em um cruzamento elegível por comparação e uma janela configurada. Cada par baseline/intervenção recebe o mesmo snapshot, demanda, janela, seed e limites do simulador.
4. Métricas da execução daquela janela, lado a lado com proveniência e limitações. A apresentação é vetorial; não existe score universal, vencedor universal ou ordenação que comprima métricas distintas.
5. Nenhuma política treinada, aprendizado durante ou entre partidas, orçamento urbano, obra, mudança de capacidade urbana ou inferência anual de efeitos de mobilidade.

“Cinco políticas” não significa cinco políticas treinadas. São regras determinísticas reproduzíveis. A baseline é referência separada, não uma sexta estratégia aprendida.

### Implementação hoje e limites de interpretação

O código disponível não corresponde integralmente a esse contrato único; o runtime tem superfícies experimentais distintas e resultados delas não devem ser misturados:

| Superfície implementada | O que o código faz hoje | Limite para este MVP |
|---|---|---|
| Comparador de mobilidade | `ArenaSignalSumoEvaluator` roda baseline e intervenção com a mesma entrada, seed e janela. A UI de comparação seleciona `node:02:04`; a janela padrão é `weekday_am_peak`. | É evidência de comparação sintética de uma intervenção em uma janela, não de cinco políticas numa partida comum nem de efeito anual. |
| Arena da API com SUMO disponível | `create_arena` monta cinco instâncias: baseline e quatro `FixedSignalTimingPolicy`; algumas alteram um nó e uma altera dois. Executa rodadas do estado urbano sintético. | Não satisfaz a contagem/configuração do MVP acima: são quatro heurísticas, não cinco, e a política coordenada pode alterar dois nós. Não usar sua saída como resultado do benchmark de um cruzamento. |
| Arena da API sem SUMO | O fallback cria cinco referências sem ação. | Não representa baseline mais cinco políticas de temporização. |
| Estado anual e créditos sintéticos | `ArenaRunner`, `AnnualRoundEngine`, `BudgetEnvelope` e contratos relacionados contêm rodadas anuais sintéticas, transições agregadas e créditos do jogo. A tarifa de sinal pode ser habilitada quando SUMO está disponível; ações de habitação e serviço permanecem indisponíveis no catálogo padrão. | Isso é implementação parcial de mecânicas sintéticas do produto, não orçamento público, obra executada, impacto urbano observado ou efeito anual de uma janela SUMO. Esses elementos ficam fora das alegações do MVP. |

As diferenças acima são lacunas de alinhamento do produto, não permissão para descrever comportamento inexistente como implementado. Até uma integração posterior, materiais do MVP devem identificar qual superfície produziu cada resultado e preservar as limitações da tabela.

`agentes-arena-v1.md` registra cinco estratégias como proposta de contrato, incluindo itens explicitamente pendentes; essa proposta não comprova cinco políticas executáveis. `rodadas-acoes-v1.md` e `contrato-evolucao-urbana-v1.md` definem relógio, orçamento e transições anuais como contratos da Arena urbana. Devem ser lidos em seu próprio escopo e não ampliam o benchmark de mobilidade por janela definido aqui.

## 3. Protocolo normativo de decisão

Cada comparação usa cópias isoladas originadas do mesmo snapshot. Antes de qualquer execução, o runtime materializa todas as observações daquela rodada; nenhuma política pode ler o estado mutável de outra cópia nem o resultado de uma política rival. As decisões são simultâneas no sentido experimental: todas recebem o estado-base congelado antes de qualquer proposta ser aplicada, mesmo que chamadas sequencialmente pelo processo.

O fluxo obrigatório é:

```text
observation → proposal → arbitration → execution → result
```

1. **Observation:** o runtime fornece somente o snapshot, a janela, a seed e os campos autorizados, com identificadores e proveniência. A observação é somente leitura e contém hash do estado observado.
2. **Proposal:** cada política devolve zero ou uma proposta tipada para a própria cópia, vinculada pelo runtime ao ID/versão congelados da política e contendo identidade da execução, hash observado e ação permitida. A proposta é uma solicitação, não uma mutação. Campos de custo enviados pela política nunca definem tarifa nem autorização.
3. **Arbitration:** o árbitro valida a proposta inteira contra o catálogo e o contexto congelado. Custos e compromissos aplicáveis são calculados pelo servidor a partir de regras versionadas. Proposta inválida, conflitante ou acima de limite é rejeitada atomicamente.
4. **Execution:** apenas uma decisão aceita é passada ao executor autorizado. Nenhum efeito é aplicado antes da arbitragem. Erro de validação, execução ou invariante não pode deixar efeito parcial; a comparação afetada falha e é marcada como tal.
5. **Result:** runtime registra proposta original, decisão, recibos, evidência do executor, métricas, hashes, versões e motivo de falha. O resultado não transforma métricas simuladas em observações.

Uma proposta rejeitada não altera estado nem aplica cobrança ou efeito parcial; recibos podem registrar custos apenas como diagnóstico da arbitragem. Ausência de ação é uma decisão válida de não intervir. Uma falha de política não deve ser silenciosamente convertida em resultado favorável ou ranqueada como execução concluída.

Para reprodução, registre ao menos snapshot/hash, configuração e hash da entrada, janela, seed, versão e limites do SUMO, IDs e versões das políticas, regras/catalogo, observação e sua hash, proposta e sua hash, decisão, artefatos e resultado. O comparador atual registra a seed, a janela, as simulações pareadas e a versão do motor na evidência; a extensão para seis políticas sob um único manifesto continua sendo integração pendente.

## 4. Dados e linguagem dos resultados

- **Synthetic / sintético:** cenário, geometria, demanda, parâmetros ou valores produzidos por gerador/configuração. Indica origem construída, não calibração nem equivalência com cidade real.
- **Simulated / simulado:** saída calculada por um modelo, aqui métricas SUMO para uma rede e janela configuradas. É consequência daquele modelo e dos seus pressupostos, não contagem observada.
- **Observed / observado:** medição proveniente de coleta empírica identificada, com fonte, período, cobertura e método documentados. O MVP descrito não fornece tráfego observado.

Relate baseline, intervenção e diferenças por métrica, unidade, janela, seed e limitações. Não some unidades incompatíveis nem declare melhoria geral sem critério registrado previamente. Métricas ausentes continuam ausentes; resultado de janela não é anualizado.

## 5. Fases e portas de entrada

As fases são incrementais. Cada uma depende de contratos e critérios de validação publicados; a presença de módulos ou tipos no repositório não satisfaz por si só esses critérios. A fase seguinte só é liberada quando sua evidência de saída estiver registrada e revisada:

1. **MVP de temporização (escopo desta especificação):** fechar a lacuna entre comparador e Arena: uma baseline e cinco políticas determinísticas, um cruzamento/ação por política, mesma entrada/seed/janela e evidência reproduzível. **Saída:** todos os critérios da seção 6 aprovados e manifesto de execução reproduzível. Não incluir score universal, orçamento urbano, obras, treinamento ou alegação anual.
2. **Interface genérica de política:** estabilizar schemas versionados para observação, proposta, falha, tempo e limites de recursos, mantendo o árbitro e os executores como autoridade. **Saída:** contrato publicado, identidade/versão vinculadas, testes de conformidade para políticas válidas e inválidas e teste que demonstre cópias sem escrita cruzada. Adicionar uma classe de política só após essa saída.
3. **Replicações pareadas e incerteza:** pré-registrar conjunto/sequência de seeds compartilhadas, quantidade de replicações, métricas, incerteza, exclusões e regra para execuções com falha. **Saída:** plano de análise versionado antes da execução e relatório que reproduza a agregação das replicações, incluindo falhas e incerteza; nenhuma conclusão é liberada só por uma seed.
4. **Novas ações viárias, uma por vez:** habilitar a próxima ação apenas com schema, elegibilidade, custo, executor, teste de rejeição atômica e evidência comparável próprios. **Saída:** catálogo versionado, testes de aceitação de ação autorizada/rejeitada, demonstração sem efeito parcial e comparação pareada da ação isolada. Só então avaliar a próxima família.
5. **Orçamento, rodadas anuais e domínios urbanos:** somente após modelos de estado, relógios, relações causais, validações, unidades e proveniência estarem especificados e validados. **Saída:** contratos versionados de cada domínio/relógio, validações reproduzíveis contra invariantes definidos e manifesto que separe estimativas sintéticas anuais das saídas SUMO por janela. Créditos de jogo não são finanças públicas.
6. **Aprendizado:** somente após baseline determinístico, protocolo de replicação e avaliação separada estarem estabelecidos. **Saída:** protocolo versionado que separa cenários/dados de treino e avaliação, limites iguais, política congelada para teste e registro de que nenhum dado reservado ou resultado de política rival foi usado para ajuste.

## 6. Critérios de aceitação

O MVP só está apto para comparação quando todos os itens forem verdadeiros:

- [ ] Proveniência do snapshot e da demanda é explicitamente sintética; entrada, janela e versão do motor são identificadas.
- [ ] Há exatamente um baseline e cinco políticas determinísticas nomeadas, versionadas e documentadas; cada política propõe no máximo uma alteração no cruzamento elegível.
- [ ] Baseline e políticas usam o mesmo snapshot, demanda, seed, janela e limites; cada uma opera em cópia isolada.
- [ ] Todas as observações são congeladas antes das propostas; decisão de uma política não altera a entrada de outra.
- [ ] Árbitro valida esquema, estado, alvo e parâmetros; calcula qualquer custo no servidor; rejeição ou erro não deixa efeito parcial.
- [ ] Propostas, decisões, executor, hashes, versões, parâmetros, seed e artefatos bastam para repetir e auditar uma execução.
- [ ] Resultados exibem métricas da janela, unidades e limitações, sem score universal, alegação anual, obra, orçamento urbano ou linguagem de observação empírica.
- [ ] Falhas, métricas ausentes, exposição de rota desconhecida e execução incompleta são reportadas sem conversão em sucesso ou zero.

## 7. Riscos e controles

| Risco | Controle obrigatório |
|---|---|
| Exploração do contrato (proposta malformada, replay, custo forjado, acesso a outra cópia ou rede) | Schemas estritos, hash/contexto vinculados, idempotência, sandbox sem rede/escrita cruzada, tarifa no servidor e rejeição atômica. Não aceitar código de participante no MVP. |
| Injustiça entre políticas | Entrada, seed, recursos, prazo, limites, versões e oportunidade de propor idênticos; regras públicas e congeladas. Registrar diferenças inevitáveis do consumo aleatório e comparar por replicação pareada. |
| Overfitting ao cenário, seed ou métrica | Políticas e regras congeladas antes do teste; múltiplas seeds pareadas em fase própria; avaliação separada; sem ajuste em resultado reservado e sem vencedor universal. |
| Proxy agregado oculta danos locais ou distributivos | Não inferir equidade, segurança ou acesso a partir de médias de rede; publicar cobertura espacial/grupos somente quando medida e validada. |
| Confundir origem e validade | Marcar cada entrada/resultado como sintético, simulado ou observado; não descrever SUMO como dado observado nem Aurora sintética como gêmeo calibrado. |
| Confundir janela com ano | Rotular período e duração da simulação; proibir anualização de métricas de janela sem modelo, hipótese e validação aprovados em fase posterior. |

## 8. Referências de implementação

- `apps/api/app/arena_mobility.py`: baseline/intervenção SUMO pareados; mesma entrada, janela e seed; limitações explícitas de escopo e não anualização.
- `apps/api/app/arena_jobs.py`: composição atual da Arena, incluindo baseline + quatro heurísticas quando SUMO está disponível e fallback de cinco referências sem ação.
- `packages/urban_arena/urban_arena/policies.py`: `DeterministicReferencePolicy` e `FixedSignalTimingPolicy`; as regras são determinísticas, não treinadas.
- `packages/urban_arena/urban_arena/actions.py`: schemas de proposta, catálogo, validação e cálculo de custo pelo servidor; a arbitragem rejeita a proposta toda quando há ação inválida.
- `packages/urban_arena/urban_arena/arena.py` e `round_engine.py`: observações congeladas, cálculo por cópia e commit atômico de registros das instâncias.
- `packages/urban_arena/urban_arena/budget.py`, `manifest.py` e contratos em `docs/especificacao/contrato-evolucao-urbana-v1.md`: orçamento em créditos e relógio/modelos anuais sintéticos são superfícies experimentais distintas do MVP de mobilidade por janela.
- `docs/especificacao/agentes-arena-v1.md` e `docs/especificacao/rodadas-acoes-v1.md`: propostas e contratos de agentes/rodadas que documentam decisões e pendências de escopos mais amplos; não são prova de que o MVP de cinco políticas esteja integrado.
- `apps/web/src/App.tsx` e `apps/web/src/ArenaPanel.tsx`: a interface identifica o comparador de janela como sintético e sem validação empírica; a Arena anual como sintética, sem ranking, vencedor ou score.
