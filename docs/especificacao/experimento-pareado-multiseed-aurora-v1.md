# Experimento pareado multi-semente e multi-janela — Aurora v1

**Status:** contrato documental versionado; ainda não implementado pela API/UI.
**Escopo:** protocolo para comparar estratégias de mobilidade com baseline em execuções SUMO sintéticas, com janelas e sementes explícitas. Este documento não altera o contrato de evolução anual da Arena nem habilita novas ações.

## 1. Pergunta e limites

O primeiro estudo responde duas perguntas condicionais à configuração congelada de Aurora: (1) sementes SUMO distintas alteram as métricas observadas? e, se houver variação mensurável, (2) qual é a distribuição dos deltas pareados entre cada estratégia e o baseline em cada janela?

Hoje a Arena avalia com seed `42` e janela `weekday_am_peak`; `weekday_off_peak` também está configurada. Rotas e horários OD são determinísticos. A entrada fornecida ao baseline e à estratégia deve ser a mesma em cada par. Portanto, variar a seed testa somente a aleatoriedade operacional que SUMO de fato usa nesta configuração; não amostra demanda.

Resultados SUMO são `simulated` e seus deltas são `derived`. Aurora, rede, demanda e intervenções são sintéticas. Uma execução representa uma janela configurada e seu escoamento, não um ano, dia típico observado ou cidade real. Não anualizar, inferir validade real, prometer efeito causal, criar ranking universal, nem interpretar precisão de Monte Carlo como redução da incerteza estrutural do modelo.

O motor anual é dono de manifesto da Arena, rodada, estado evolutivo, ações e indicadores anuais. O SUMO é um avaliador opcional e isolado por janela. Sua saída pode ser referenciada como evidência de mobilidade da rodada; não altera o estado urbano, não produz indicador anual e não é somada a resultados de outras janelas.

## 2. Manifesto imutável e identidade

Antes de agendar qualquer execução, criar um manifesto canônico, validado e imutável. O manifesto tem `protocol_id: aurora-paired-multiseed-v1`, `protocol_version: 1`, `experiment_id`, data de criação e hash SHA-256 de sua serialização canônica. Uma alteração de qualquer entrada exige novo `experiment_id` e novo hash; não se edita um experimento iniciado.

O manifesto registra, no mínimo:

- cidade/configuração e versão, `snapshot_id` e hash do snapshot;
- lista ordenada e sem duplicatas de `window_id` selecionadas, horários, fuso se aplicável, unidade temporal e hash da configuração da janela; disponibilidade configurada não significa seleção automática;
- políticas/estratégias avaliadas, baseline identificado e hash/versionamento imutável de cada política, proposta e intervenção;
- lista explícita de seeds inteiras não negativas e escopo `sumo_operational_randomness`; registrar método de seleção/geração e, se aplicável, seed mestre. Não chamar esse campo de seed de demanda;
- identidade e hash da demanda expandida por janela, incluindo rotas, contagens, horários de partida e regras de escoamento. O manifesto distingue `demand_hash` da seed SUMO;
- `drain_limit_seconds`, método/versão de cálculo das métricas, versões do SUMO, adaptador, runtime, dependências relevantes e código executado (commit SHA/container digest);
- métricas primárias/secundárias, unidade, cobertura temporal e regra de comparação/IC;
- limites de execução e orçamento máximo (seção 8), número máximo de tentativas e política de retry;
- rótulos de proveniência e limitações científicas obrigatórias para apresentação.

Uma célula lógica de execução tem chave determinística derivada de `experiment_id`, versão do manifesto, estratégia, janela, seed, hash de entrada efetiva, limite de escoamento e versões de engine/adaptador. Uma comparação é identificada por `pair_id`, derivado da chave do experimento, janela, seed, estratégia e baseline. Os hashes incluem a intervenção aplicada em cada braço; não substituem os hashes das entradas comuns.

Qualquer identidade repetida com o mesmo conteúdo é idempotente. A mesma chave com conteúdo diferente é conflito e não pode sobrescrever resultado. Reordenação cosmética do JSON deve gerar a mesma serialização canônica; mudança substantiva sempre cria identidade nova.

## 3. Matriz e unidade experimental

O plano é o produto cartesiano declarado `estratégia × janela × seed`. A unidade de relatório é uma célula `(estratégia, window_id, seed)` e, para comparação, um bloco pareado `(estratégia, baseline, window_id, seed)`. Para cada bloco são executados baseline e estratégia; são duas simulações SUMO por par, mesmo se uma implementação futura reutilizar baseline idêntico. Reuso só é permitido por identidade idêntica e precisa aparecer como referência explícita ao mesmo resultado, sem contabilizar execução duplicada.

Baseline e estratégia devem usar exatamente o mesmo snapshot, rede, demanda expandida, janela, seed, limites de escoamento, configuração de coleta e versões. A única diferença autorizada é a política/intervenção declarada. A igualdade é comprovada por hashes de entrada comparáveis, não apenas por igualdade de rótulos. Uma comparação que viole paridade é inválida e não gera delta.

Seeds diferentes formam réplicas Monte Carlo condicionais ao protocolo, desde que cada seed corresponda a entrada e execução identificadas. Rodar de novo a mesma seed com os mesmos bytes de entrada é repetição técnica para verificar determinismo/reprodutibilidade, não uma nova réplica independente. O mesmo conjunto de seeds pode ser usado nas duas janelas; nesse caso cada seed é um bloco medido em duas janelas, não duas seeds independentes. Resumos e incerteza continuam calculados separadamente por janela.

## 4. Piloto e dimensionamento

### 4.1 Piloto de sensibilidade à seed

Executar primeiro um piloto cujo plano, métricas, seeds, janelas selecionadas e orçamento sejam congelados antes de iniciar. Manter rede, snapshot, demanda, estratégia, limites, versão e método de cálculo fixos; variar somente a seed. Para cada janela selecionada, executar baseline e cada estratégia em pares completos. Comparar também saídas repetidas com mesma seed/entrada em um subconjunto pré-declarado para detectar não determinismo técnico, sem tratá-las como réplicas.

O relatório do piloto deve mostrar, para cada métrica e janela, se houve variação entre seeds nos braços e nos deltas. Se não houver variação, a conclusão permitida é “nenhuma variação observada nas seeds testadas sob esta configuração”. Isso não prova variância populacional zero, robustez geral ou validade do simulador. Se a seed não afetar a saída, réplicas repetidas não contam como evidência de robustez e não justificam dimensionar uma comparação inferencial por seed.

Se a pergunta seguinte exigir sensibilidade de demanda, criar outro experimento/protocolo com `demand_scenario_id` e hash próprios, variando explicitamente volumes/perfis/OD. Analisar deltas dentro de cada cenário de demanda. Não misturar a variância de seed com variação de demanda; um desenho cruzado seed × demanda requer nova identidade, orçamento do produto cartesiano e método que modele os dois fatores.

### 4.2 Escolha de réplicas após o piloto

Não há tamanho de amostra padrão neste contrato. O responsável declara métricas primárias, precisão alvo `h` (semi-largura máxima do IC da média do delta), nível de confiança, custo por execução e orçamento antes de dimensionar. Para cada janela e métrica primária, uma aproximação inicial para planejar `n` sementes é `n ≈ (t* × sΔ / h)²`, onde `sΔ` é o desvio-padrão piloto dos deltas pareados e `t*` usa o nível e graus de liberdade planejados. Reavaliar com margem conservadora porque `sΔ` piloto é incerto; não declarar tamanho suficiente se o custo correspondente exceder o teto.

Dimensionamento e critério de parada se aplicam por janela e métrica primária. Um limite sequencial de parada por precisão exige método de cobertura sequencial declarado antes da coleta. Caso contrário, calcular o IC apenas no `n` planejado. Não parar repetidamente quando um IC nominal de 95% aparentar resultado favorável. Se o teto de custo for atingido antes da precisão alvo, concluir “precisão alvo não atingida dentro do orçamento”, com dados incompletos/limite explícitos.

## 5. Resumos, dispersão e incerteza

Publicar sempre os resultados por execução e resumir separadamente por `(window_id, estratégia, métrica)`. Nunca juntar linhas de janelas em um único `n`, média ou IC. Não somar resultados entre seeds para formar uma observação artificial e não anualizar.

Para cada braço, janela e métrica, reportar número planejado/concluído, média, desvio-padrão amostral, mediana, intervalo interquartil e mínimo/máximo. Para estratégia versus baseline, calcular primeiro por seed o delta pareado `Δ = estratégia − baseline` na mesma janela; reportar a distribuição dos deltas com média, desvio-padrão, mediana, intervalo interquartil e extremos. Sinal favorável depende da métrica e deve ser documentado; não converter unidades para score composto.

Para a média do delta, o método primário de IC é IC t bilateral de Student de 95% sobre os `n` deltas pareados: `média(Δ) ± t(0,975; n−1) × sΔ/√n`. Declarar `n`, graus de liberdade, nível, estimador e hipótese de sementes independentes como blocos Monte Carlo. Se a distribuição for fortemente assimétrica ou dominada por extremos, reportar adicionalmente bootstrap pareado por seed (percentil, 10.000 reamostragens com reposição, PRNG e seed mestre do bootstrap registrados); ele é análise de sensibilidade e não substitui silenciosamente o método primário. Com menos de duas unidades pareadas válidas, não calcular dispersão amostral nem IC; com poucos seeds, marcar a estimativa como exploratória. ICs representam incerteza Monte Carlo condicional ao manifesto, não incerteza do SUMO, da rede, parâmetros, demanda ou tráfego real.

Fixar métricas primárias antes da execução. Métricas secundárias são descritivas; se forem usadas para múltiplas alegações confirmatórias, declarar método de controle de multiplicidade previamente. Para médias de tempo/velocidade sobre viagens concluídas, publicar junto contagens solicitadas, concluídas e não concluídas: composição diferente de viagens concluídas pode mudar a média. Preservar a semântica existente: filas cobrem a janela de demanda, tempo/velocidade cobrem as viagens concluídas até o fim do escoamento.

## 6. Falhas, incompletude e retry

Estados do experimento: `queued`, `running`, `succeeded`, `partial`, `failed`, `cancelled`. Estados da execução: `queued`, `running`, `succeeded`, `failed`, `cancelled`. Toda execução conserva identidade, início/fim, tentativa, status, erro estável e referências de artefato. Métricas de execução falha/cancelada são `null`; não publicar resultados parciais do SUMO como métricas completas.

Falha de um braço invalida seu par. Falha de célula não apaga outras células concluídas, mas o experimento só é `succeeded` quando todas as células obrigatórias estão completas. Pode-se disponibilizar `partial` para diagnóstico com faltantes enumerados e sem apresentar estatísticas finais como completas. IC/resumo definitivo exige conjunto completo previsto para a janela; qualquer política diferente de inclusão de faltantes precisa estar pré-registrada e ser exposta junto aos resultados.

Retry mantém a mesma chave de célula/par e incrementa `attempt`; reutiliza resultados já confirmados e agenda apenas execuções faltantes/falhadas recuperáveis. A resposta idempotente distingue retry de nova réplica. Conteúdo divergente sob mesma identidade resulta em `conflict`. Cancelamento não converte saída parcial em sucesso. Reinício de processo não pode levar a duplicação nem apagar execuções confirmadas; uma implementação sem armazenamento durável deve declarar que não satisfaz este requisito.

## 7. Persistência, proveniência e DTO para API/UI

Persistir o manifesto original, seu hash, matriz planejada, estado de cada célula/par/tentativa, hashes e cópias imutáveis das entradas efetivamente consumidas, saída bruta necessária à auditoria, métricas normalizadas, logs/erros estáveis, referências e checksums de artefatos, versões, instante, custo observado e relatório estatístico. Registrar proveniência `synthetic_config`, `synthetic_generated`, `simulated` e `derived` conforme o artefato; nunca rotular saída Aurora como `observed`.

A API futura expõe DTOs tipados, com schema versionado, sem cálculo estatístico no navegador e sem campos de domínio anual confundidos com SUMO. Estrutura mínima:

```json
{
  "experiment": {
    "experiment_id": "<id>",
    "protocol_id": "aurora-paired-multiseed-v1",
    "protocol_version": 1,
    "manifest_sha256": "<sha256>",
    "status": "running",
    "planned_cells": 0,
    "completed_cells": 0,
    "failed_cells": 0,
    "provenance": "simulated",
    "limitations": ["synthetic_aurora", "window_only", "network_aggregated", "not_causal", "not_real_world_validated"],
    "pairs": [
      {
        "pair_id": "<id>",
        "strategy_id": "<id>",
        "baseline_execution_id": "<id>",
        "strategy_execution_id": "<id>",
        "window_id": "weekday_am_peak",
        "seed": 42,
        "common_input_sha256": "<sha256>",
        "status": "succeeded",
        "baseline_metrics": {"<metric_id>": {"value": 0, "unit": "<unit>", "period": "window_plus_drain"}},
        "strategy_metrics": {"<metric_id>": {"value": 0, "unit": "<unit>", "period": "window_plus_drain"}},
        "deltas": {"<metric_id>": {"value": 0, "unit": "<unit>", "direction": "strategy_minus_baseline"}},
        "route_exposure": "unknown",
        "attempts": 1,
        "error": null
      }
    ],
    "summaries_by_window": [
      {
        "window_id": "weekday_am_peak",
        "strategy_id": "<id>",
        "metric_id": "<id>",
        "unit": "<unit>",
        "n_planned": 0,
        "n_complete": 0,
        "arm_summary": {"mean": null, "sd": null, "median": null, "iqr": null, "min": null, "max": null},
        "paired_delta_summary": {"mean": null, "sd": null, "median": null, "iqr": null, "min": null, "max": null},
        "confidence_interval": {"method": "student_t_paired", "level": 0.95, "lower": null, "upper": null, "n": 0, "degrees_of_freedom": null, "interpretation": "conditional_monte_carlo_only"}
      }
    ]
  }
}
```

O exemplo ilustra nomes e nulabilidade, não valores permitidos ou formato final de endpoints. IDs de execução têm métricas próprias, seed, janela, hashes de entrada e versão SUMO; o DTO também carrega unidades, período, status e avisos. `route_exposure` é um sinal descritivo de que alguma rota completa cruza nó alterado; `exposed` não identifica veículos afetados nem estima efeito neles. Mesmo quando `exposed`, métricas e deltas seguem agregados na rede. Ausência/inconsistência do artefato de rotas deve ser `unknown`, nunca `not_exposed` por inferência.

## 8. Custo máximo e parada operacional

Todo manifesto contém limites finitos pré-execução: `max_sumo_runs`, `max_attempts_per_cell`, `max_wall_clock_seconds_per_run`, `max_total_wall_clock_seconds` e, quando suportado pelo executor, limites de CPU, memória e armazenamento. A matriz deve ser precificada antes do agendamento: o número máximo de execuções inclui baseline e estratégia para cada par, mais todas as tentativas permitidas. Reuso de uma execução idêntica só reduz custo se comprovado por identidade e fica auditável.

O executor rejeita plano cujo custo-limite calculado ultrapasse qualquer teto; não inicia execução sem limites e estimativa. Durante a execução, interrompe novo agendamento/retry quando o próximo trabalho excederia `max_sumo_runs`, custo total ou número de tentativas. Uma execução em andamento para ao atingir seu timeout/limite; registra resultado como falha ou cancelamento, nunca como sucesso. Reportar custo planejado versus realizado por janela, seed, braço e tentativa. Infraestrutura deve definir valores efetivos do teto antes de criar o manifesto; este contrato não inventa custo monetário nem tamanho amostral universal.

Stop criteria científicos/operacionais: (a) parar o piloto ao atingir seu orçamento máximo ou quando o teste pré-declarado de sensibilidade à seed tiver cobertura planejada; (b) ampliar/dimensionar somente com base em variabilidade piloto e precisão alvo por janela; (c) parar a expansão ao atingir o custo máximo, timeout, falhas acima do limite pré-declarado ou precisão alvo; (d) declarar explicitamente precisão não atingida quando custo limitar `n`; (e) nenhuma parada baseada em sinal favorável de IC nominal consultado repetidamente.

## 9. Critérios de aceite e testes necessários

O protocolo/documentação e sua implementação futura só são aceitáveis quando:

1. O manifesto é canônico e imutável; hashes, IDs, versões e orçamento permitem reconstruir a matriz e identificar toda entrada/saída.
2. Matriz cobre cada combinação declarada sem duplicatas; baseline/estratégia têm paridade de entrada comprovada, e diferença não autorizada invalida o par.
3. Variação de seed e cenário de demanda são fatores separados; relatório nunca chama seeds repetidas/sem variância de evidência suficiente de robustez.
4. Resumos, dispersão e IC usam unidade por seed e permanecem segregados por janela; fórmula/método, n, níveis, pressupostos e faltantes aparecem no DTO/relatório.
5. Falha, cancelamento, retry, submissão duplicada e divergência de conteúdo seguem estados/idempotência especificados; métricas parciais não são apresentadas como completas.
6. Teto de trabalho e tentativas é verificado antes e durante execução; custo estimado/realizado e motivos de parada são auditáveis.
7. Artefatos e métricas têm proveniência; API/UI distingue indisponível de zero e exibe limitações sintéticas, temporais, agregadas e não causais.

Testes necessários na implementação (não executados por esta entrega documental):

- hash/canonicalização do manifesto, imutabilidade e conflito de mesma chave com payload diferente;
- geração da matriz cartesiana e rejeição de janela/seed duplicada ou não configurada;
- paridade exata de hashes para baseline/intervenção e rejeição de par divergente;
- demanda expandida idêntica entre seeds no protocolo de seed, verificando que só varia seed operacional;
- métricas determinísticas por célula e resumo de cada janela isolado, incluindo fórmula do delta e IC t; casos n=0, n=1 e bootstrap de sensibilidade;
- completude, faltantes, status `partial`, falhas em cada braço, cancelamento e retomada sem duplicar resultados confirmados;
- retry concorrente/idempotência e persistência após reinício;
- orçamento, timeout, limite de tentativas, custo agregado e parada no limite sem agendar trabalho excedente;
- DTO/OpenAPI: nulabilidade, unidades, períodos, estados, erros, proveniência e enum de `route_exposure`; UI nunca apresenta `unknown` como ausência de exposição;
- regressão dos contratos atuais de execução SUMO por janela e fronteira: nenhuma métrica de janela é anualizada ou incorporada a indicador anual.

## 10. Revisões incorporadas

- **Architect (revisão de contrato/fronteiras):** SUMO permanece evidência opcional por janela, fora do estado e indicadores anuais; manifesto deve separar seed operacional de hash de demanda; DTO deve representar pares tipados; `route_exposure` não atribui efeito individual.
- **Test-engineer:** identidade por célula/par, idempotência e retomada, matriz de custos incluindo retries, completude antes de resumo, invariantes de reconciliação e testes de contrato.
- **Critic (validade estatística):** unidade é bloco de seed pareado por janela; dispersão de braço e dispersão de delta são quantidades distintas; IC condicional não valida mundo real; ausência de variação nas seeds testadas não prova robustez; sensibilidade de demanda é outro experimento.

## 11. Referências e compatibilidade

- [Contrato de evolução urbana v1](contrato-evolucao-urbana-v1.md): separação entre domínios anuais e integração SUMO.
- [Catálogo de indicadores v1](catalogo-indicadores-v1.md): semântica temporal, unidades e proveniência das métricas SUMO.
- [Contrato integrado da Arena v1](contrato-integrado-arena-v1.md): snapshot, proveniência sintética e ausência de anualização.
- [Contrato inicial dos jobs SUMO](../execucao/prompts-mvp1-4-chats.md): métricas por execução, semântica de janela/escoamento, paridade e limitações de `route_exposure`.

Este documento é o handoff documental para o Chat API. A implementação futura deverá propor endpoints, armazenamento, schemas e migrações compatíveis com este contrato antes de ligar a UI; nenhuma API ou UI foi implementada como parte desta especificação.
