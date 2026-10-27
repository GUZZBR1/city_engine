# Contrato integrado de evolução anual de Aurora — v1

**Status:** contrato-alvo congelado para a primeira implementação de evolução urbana. **Não implementado nem validado empiricamente.**

Este documento é normativo para a integração v1 e prevalece sobre recomendações anteriores quando declarar uma resolução. Os seis documentos de domínio e estado nesta pasta preservam a origem das propostas; conflitos explicitamente resolvidos abaixo devem ser corrigidos nas cópias desta branch antes da implementação. Os worktrees e arquivos-fonte das outras branches não são alterados.

## 1. Escopo, relógio e semântica

- `aurora-base-v1` é um benchmark sintético imutável. Cada instância recebe estado isolado, proveniente do mesmo snapshot inicial e hash.
- Uma rodada urbana `r` representa o ano sintético `r`, de 1 a 10. O horizonte padrão é 10; rodada 11 é inválida salvo novo experimento versionado.
- O perfil anual obrigatório é `aurora_synthetic_v1`. No início do experimento ele materializa e registra os defaults versionados dos modelos listados na seção 4. Não existe rodada anual parcial silenciosa: parâmetro obrigatório ausente/inválido falha a configuração ou a execução; grandeza sem insumo mensurável publica `null` e motivo.
- O ano sem ação **ainda executa os modelos anuais de referência**. `no_action` significa proposta vazia, sem intervenção discricionária, e não significa cidade congelada.
- O ciclo atualmente implementado que preserva hash e não executa domínio recebe no contrato integrado o nome `protocol_noop`, com `domain_transition=not_run`. A implementação existente não pode ser apresentada como `no_action` anual nem como simulação científica de um ano. A migração do identificador atual é explícita e versionada.
- Cada execução é determinística para o mesmo estado pai, configuração, versões, eventos e sementes. Sem evidência independente, resultados descrevem somente o benchmark sintético.

## 2. Estado, identidade e commit

O estado inicial permanece referência imutável. Cada transição constrói um candidato profundo separado, identificado por `(experiment_id, instance_id, round_index, transition_version, parent_city_state_hash)`. Calcular novo `city_state_hash` sobre payload canônico; manter separado o hash encadeado do registro da rodada. Uma instância nunca compartilha estado mutável com outra.

O commit publica em uma unidade lógica o novo estado, efeitos/compromissos, indicadores calculados, decisão da proposta e registro da rodada. Validar hash pai por compare-and-swap. Falha, cancelamento ou invariante violada antes do commit preserva o último estado confirmado. Retry idêntico é idempotente; mesma identidade com conteúdo diferente é conflito. O armazenamento atual em memória cobre somente o processo atual e não satisfaz persistência durável ou concorrência entre processos.

## 3. Ordem canônica de uma rodada

1. Carregar estado confirmado, snapshot raiz e manifesto versionado.
2. Criar candidato isolado e aplicar efeitos pendentes cuja `effective_round` seja `r`.
3. Congelar e entregar a observação desse candidato. Todas as propostas da mesma instância usam essa observação; ela não inclui decisões novas de `r`.
4. Receber no máximo uma proposta por instância/rodada; proposta vazia é `no_action`.
5. Validar schema, autoridade, alvos, pré-condições, unidades, limites, conflitos e orçamento pelo servidor. Rejeição de item ou conflito interno rejeita o pacote atômico; não há aceitação parcial.
6. Aplicar efeitos imediatos permitidos no candidato (v1: plano semafórico para a próxima janela SUMO configurada da própria rodada) e agendar efeitos atrasados com rodada efetiva explícita.
7. Executar exatamente uma vez cada modelo anual obrigatório de `aurora_synthetic_v1`, na ordem: população → habitação → empregos → capacidade/demanda de serviços → área verde → estimativa anual de CO₂e. Todos usam o estado candidato e eventos efetivos desta rodada. Mobilidade só roda quando solicitada, nas janelas configuradas, e nunca é anualizada. Outros indicadores continuam no resultado com `null` e motivo quando os insumos necessários não existem.
8. Validar balanços, calcular métricas disponíveis e hashes. Insumos ausentes geram `null` com motivo; nunca zero ou imputação silenciosa.
9. Confirmar o commit atômico e publicar o resultado. Nenhum estado ou indicador parcial fica visível como resultado concluído.

Uma mudança semafórica aprovada após a observação não altera retroativamente o que o agente viu. Habitação e contratos de serviço, quando forem habilitados em versão futura, entram em vigor em `r+1` conforme seus eventos. Efeitos vencidos aparecem na observação de `r`.

## 4. Modelos v1 e limites de interpretação

Os modelos e defaults definidos nos documentos acompanhantes são **hipóteses sintéticas configuráveis**, não parâmetros científicos calibrados. O perfil obrigatório `aurora_synthetic_v1` materializa esses defaults antes da rodada e os guarda no manifesto; substituir ou retirar um default cria nova versão do perfil:

- **População:** nascimentos, mortes e saldo migratório determinísticos por zona; limitar migração negativa para impedir população negativa e registrar parcela bloqueada.
- **Habitação:** estoque urbano inicial de 22.178 unidades é derivado por regra declarada de 21.069 domicílios ocupados urbanos e 5% de vacância sintética; não altera o campo existente de 24.104 domicílios ocupados totais. Construção/retirada é limitada; demanda sem unidade não remove residentes.
- **Empregos:** evolução por taxa própria e alocação determinística aos cinco distritos urbanos; entorno permanece sem empregos configurados.
- **Serviços:** cálculos agregados de escola e atenção primária nos cinco distritos urbanos. Não representam acesso geográfico, qualidade ou atendimento observado; o entorno rural fica indisponível.
- **Área verde:** área agregada configurada sinteticamente, sem inferência de polígonos a partir de `land_use`; não mede acesso, qualidade ecológica ou segurança.
- **CO₂e:** estimativa condicional a veículo-km/ano e fator sintéticos configurados. É exógena às janelas SUMO nesta versão e **não pode ser atribuída como impacto de uma intervenção de tráfego**. Não representa concentração atmosférica.
- **Mobilidade:** resultados SUMO permanecem métricas das janelas executadas, com escoamento e semente declarados; não multiplicar nem extrapolar para um ano.

Sem atividade/fator ambiental válido, inventário completo ou denominador aplicável, publicar `null` e o motivo (`missing_input`, `unknown_coverage` ou `not_applicable`). SER-01 (acesso geográfico), AMB-02 (concentração), métricas de equidade e cobertura rural permanecem indisponíveis.

## 5. Orçamento e ações

O envelope configurado permanece **100 CS = 60 operações fixas + 10 reserva + 30 discricionários**. CS não se converte em BRL. Operações fixas não são verba de ação; a reserva é indisponível a agentes e expira no fecho; o teto discricionário reinicia em 30 a cada rodada. Não há carry-over, caixa, receita, dívida ou juros.

Custos são calculados pelo servidor a partir do catálogo versionado. Aprovação de custo recorrente reserva a parcela futura dentro do teto de 30 CS da respectiva rodada; a proposta só é aceita se couber em todas as rodadas comprometidas até o horizonte congelado. Compromisso futuro não é dinheiro acumulado. Não há financiamento após a última rodada. `budget_request` do agente é apenas anotação.

| Ação | Estado no contrato v1 | Tarifa sintética proposta | Efeito |
|---|---|---|---|
| `signal_timing_change` | Única ação candidata a habilitação inicial; só pode ser anunciada pelo runtime quando adaptador SUMO, alvo, validação e execução comparável estiverem ligados ao orquestrador. | 2 CS na aprovação + 1 CS de operação na rodada; 3 CS no total por aplicação. | Altera plano de nó existente e afeta apenas a próxima janela SUMO configurada na rodada. Não muda demanda, população ou emissões anuais. |
| `housing_add_units` | **Desabilitada** até existir capacidade edificável por distrito e validação do alvo/limite no estado evolutivo. | 8 CS por pacote de 10 unidades; custo pontual. | Capacidade ativa em `r+1`; não cria residentes nem domicílios ocupados. |
| `service_capacity_contract` | **Desabilitada** até fixar `service_type`, unidade, distrito/instalação, capacidade-base e limite validável. | 6 CS de preparação em `r` + 2 CS recorrentes em `r+1`. | +10 unidades tipadas de capacidade apenas em `r+1`; expira ao fim dessa rodada. |

Tarifas, limites e valores são configuração sintética de demonstração, não custos reais. Uma ação sem alvo, unidade, tarifa, pré-condição ou período completos é indisponível, nunca custo zero. Uma proposta é pacote atômico; conflitos internos rejeitam o pacote. Instâncias concorrentes são cópias independentes; somente compare-and-swap no estado pai resolve workers concorrentes sobre a mesma instância.

## 6. Indicadores e proveniência

O catálogo existente mantém os IDs canônicos. As propostas de domínio mapeiam assim:

- `SER-02a` e `SER-02b` são subindicadores versionados com `base_indicator_id=SER-02`: `service_type=school` (vagas/ano letivo) e `service_type=primary_health` (consultas/ano). Nunca agregar volumes de unidades diferentes; percentuais agregados são recalculados de numeradores e denominadores compatíveis.
- `SER-03` pode ser publicado somente se volume atendido e capacidade operacional tiverem definições compatíveis; a regra sintética `served=min(demand,capacity)` não prova atendimento real.
- `AMB-01a` é subindicador **com ID e versão próprios** e `base_indicator_id=AMB-01`: estimativa anual sintética a partir de atividade veículo-km exógena explicitamente indicada. Não agregar nem comparar diretamente com emissões SUMO por janela, nem usar para declarar benefício ambiental de ação semafórica.
- `AMB-03a` é subindicador versionado com `base_indicator_id=AMB-03`: razão agregada sintética/derivada, limitada aos cinco distritos urbanos e sem alegação de cadastro espacial real.
- IDs canônicos MOB continuam restritos à janela SUMO; não transformar resultados de janelas em indicadores anuais.

Todo valor publicado inclui: indicator ID/versão, valor ou `null`/motivo, unidade, período, território e cobertura, numerador/denominador aplicáveis, fórmula/método e versão, estado pai/resultado, parâmetros/fontes, limitações e produtor.

Proveniência separa **origem** de **método**: `source_kind ∈ {synthetic_config, synthetic_generated, external_dataset, observed}` e `production_method ∈ {measured, derived, simulated, estimated}`. Uma origem `observed` exige fonte, licença, cobertura e período auditáveis. Defaults sintéticos nunca recebem esse rótulo. Arquivos Kaggle sintéticos são `external_dataset` + `simulated`/`derived`; não substituem observações nem validam Aurora.

## 7. Política de agentes, conflitos e avaliação

Cada participante recebe estado, orçamento e observação isolados. Propostas simultâneas são avaliadas contra a mesma observação prévia. No máximo uma proposta por instância/rodada. A proposta com ações internamente incompatíveis é rejeitada integralmente; sem uma política concorrente adicional versionada, não há desempate por ordem de chegada.

Não há score universal, ranking agregado ou vencedor computado por esta versão. Comparações permanecem multidimensionais, com valores, unidades, incerteza e critérios de elegibilidade separados. O agente pode propor, mas não calcular autoridade de custo nem editar diretamente o estado.

## 8. Critérios de aceite da implementação

1. `protocol_noop` preserva hash de cidade e emite `domain_transition=not_run`; `no_action` anual executa exatamente uma vez todos os modelos obrigatórios de `aurora_synthetic_v1`. `round_record_hash` e `round_index` avançam sempre; `city_state_hash` é baseado no conteúdo e pode repetir se o conteúdo final for idêntico ao anterior.
2. Dez rodadas usam `round_index=synthetic_year=1..10`; 11 é rejeitada pelo horizonte padrão.
3. Todos os balanços de população, empregos, habitação, serviços e orçamento fecham; desemprego/habitação não atendida nunca remove residentes por regra implícita.
4. Compromissos recorrentes respeitam 30 CS em cada ano futuro e não ultrapassam o horizonte; retry não cobra nem aplica efeitos em duplicidade.
5. Efeitos atrasados só entram na rodada declarada; plano semafórico aceito antes do SUMO afeta a janela daquela rodada sem alterar observação já entregue.
6. Falha injetada em cada estágio antes do commit não altera estado confirmado nem indicadores publicados; falha fica registrada como diagnóstico não científico.
7. Ausência de dado produz `null` + motivo. Unidades incompatíveis, valor não finito, limite violado ou configuração sem versão falham antes do commit.
8. Um mesmo manifesto, estado pai, eventos, ações, versões e sementes reproduz payload canônico e hashes segundo tolerância declarada por modelo; hash de estado é igual se, e somente se, o payload canônico for igual, enquanto o registro de rodada avança.
9. Saída SUMO é rotulada por janela; estimativa anual sintética de CO₂e é explicitamente exógena; nenhum dataset sintético aparece como `observed`.
10. Nenhuma métrica indisponível vira zero; nenhuma métrica individual ou multidimensional é comprimida num score global.

## 9. Sequência de implementação e bloqueios

1. Adicionar `transition_version`, schema de estado evolutivo, parâmetros materializados e proveniência ortogonal; manter YAML e snapshot inicial compatíveis.
2. Implementar transições determinísticas de população/habitação/empregos com estado candidato, balanços e hashes.
3. Integrar capacidade/demanda de serviços, área verde e emissão sintética, com `null` e motivos para insumos ausentes.
4. Atualizar o orquestrador para distinguir `protocol_noop` de `no_action` anual, ordem canônica, manifesto, atomicidade e commit.
5. Integrar ação semafórica e seu job SUMO somente depois dos passos anteriores e publicar a ação apenas quando executável. Habilitar habitação/serviços em outra versão depois de inventários e contratos tipados.
6. Implementar persistência durável e isolamento multiworker antes de alegar garantias operacionais além do armazenamento em memória.
7. Datasets externos entram primeiro como fixtures separadas com manifestos/licenças; aquisição de dados reais para validação é outra trilha e requer geografia, período, proveniência e observações independentes compatíveis.

## 10. Fontes normativas e precedência

Este contrato integra as fontes nesta pasta:

- `contrato-integrado-arena-v1.md` — protocolo de referência atual e seus limites.
- `estado-cidade-v1.md` — campos existentes, totais e identidade.
- `rodadas-acoes-v1.md` — validação, simultaneidade, atomicidade e reprodução.
- `catalogo-indicadores-v1.md` — fórmulas e status de prontidão.
- `transicoes-populacao-habitacao-v1.md` — população, habitação e empregos.
- `transicoes-servicos-ambiente-v1.md` — serviços, área verde e CO₂e sintético.
- `orcamento-acoes-sinteticas-v1.md` — tarifas e catálogo demonstrativo.

Onde fontes antigas ainda disserem que `no_action` não avança domínios, isso se refere apenas ao ciclo legado `protocol_noop`. Para a implementação-alvo v1, este contrato prevalece. Onde o orçamento geral deixar recorrência, saldo ou reserva em aberto, valem as decisões da seção 5. Demais hipóteses específicas permanecem propostas sintéticas, configuráveis e substituíveis por versão; “congelado” significa contrato de software v1, não validação científica.
