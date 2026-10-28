# Agentes decisores da Urban Twin Arena — especificação v1

**Status:** proposta de contrato; interfaces de agente ainda não implementadas  
**Escopo:** cinco políticas decisoras em cópias independentes de Aurora e duas políticas de referência  
**Base:** [conceito da Arena](../conceito/urban-twin-arena.md), [arquitetura completa](../arquitetura/arquitetura-completa-urban-twin-arena.md), [especificação de Aurora sintética](../arquitetura/cidade-sintetica-urban-twin-arena.md) e `configs/cities/aurora-base-v1.yaml`

## 1. Propósito e vocabulário

Esta frente especifica **agentes decisores da Arena**: políticas de software que recebem informação permitida sobre uma cópia de Aurora e propõem ações para aquela cidade. Cada agente concorre sob os mesmos objetivos, regras e recursos computacionais. Ele não controla a simulação nem altera diretamente o estado.

Esses agentes são componentes do **produto Urban Twin Arena**. Não são subagentes Codex, não são pessoas ou serviços de revisão de código e não participam da implementação do repositório. Subagentes Codex `architect`, `verifier` ou `executor` são ferramentas de colaboração usadas durante o desenvolvimento; não são executados nas partidas, não recebem cópias de Aurora e não contam entre os cinco participantes.

A Arena avalia políticas sob condições declaradas. Não presume encontrar uma política universalmente ótima nem atribui validade empírica a resultados da cidade sintética.

## 2. Estado da proposta

| Tema | Já existe na documentação/repositório | Proposta nesta especificação | Pendente de contrato ou decisão |
|---|---|---|---|
| Aurora | `aurora-base-v1.yaml`, snapshots/configuração de cidade e simulação de mobilidade por janela com semente | Instanciar cópia independente por participante e por replicação | Snapshot completo mutável por rodada e contrato de clone para a Arena |
| Participantes | Configuração prevê cinco cópias de agentes, `no_action` e `fixed_rule`; docs descrevem cinco agentes e duas referências | Definir cinco papéis estratégicos distintos e duas referências operacionais | Identidade/artefatos e critérios de aprovação de cada política |
| Entrada/saída | A arquitetura propõe `Observation` e `ActionProposal` tipados; há contratos de simulação, não contrato executável de agente | Especificar envelope sem inventar propriedades da cidade | Schemas concretos de observação, rodada e ação, unidades, alvos e versão |
| Regras e orçamento | Aurora define 100 créditos simulados/rodada: 60 operações fixas, 10 reserva, 30 discricionários; configuração permite `no_action` | Árbitro como autoridade única de regras, custos e aplicação | Custos/precondições de cada ação, carry-over, receita, conflito e regra de execução atômica |
| Resultados | Mobilidade tem métricas e proveniência de execução; documentação propõe vetor multidimensional/Pareto | Avaliar resultados em dimensões, territórios e grupos quando medidos | Catálogo de indicadores da Arena, granularidade espacial/social e thresholds de segurança |
| Operação | Simulação roda com limites e registra seed, versão SUMO e artefatos | Execução isolada de política e auditoria ponta a ponta | Protocolo de sandbox, limites numéricos, timeout por chamada e política de falhas |

**Leitura de status:** o que aparece na coluna “já existe” é configuração, implementação parcial ou decisão registrada em documentação; não significa que a Arena completa já esteja implementada. A arquitetura e esta especificação são propostas até sua implementação e validação.

## 3. Participantes

Cada partida tem cinco agentes de estratégia e duas referências. O experimento fixa um mesmo vetor de objetivos mensuráveis, restrições, observabilidade, ações permitidas e orçamento para todos; as políticas diferem na regra de decisão e prioridade que aplicam a esse vetor. Os rótulos abaixo identificam objetivos de desenho, não algoritmos ou vantagem presumida. Preferências específicas (incluindo pesos e desempates) precisam ser explícitas e congeladas, sem alterar os objetivos ou regras comuns.

| ID provisório | Estratégia a comparar | Intenção de política | Risco/hipótese a observar |
|---|---|---|---|
| `cost_guard` | Conservação fiscal | Preferir ações com custo total menor e evitar compromissos recorrentes quando houver alternativas eficazes | Pode conservar recursos às custas de serviço ou acesso |
| `access_equity` | Acesso e equidade | Priorizar redução de disparidades entre territórios/grupos, respeitando pisos e dados de cobertura | Depende de indicadores desagregados e regra explícita de equidade |
| `mobility_flow` | Fluxo e mobilidade | Buscar melhorias nas medidas de mobilidade cobertas pelo modelo, respeitando segurança e capacidade | Pode melhorar médias agregadas enquanto piora grupos ou áreas |
| `resilience` | Robustez a cenários | Usar regra conservadora declarada para o cenário adverso conhecido na observação; avaliar o desempenho em um conjunto pré-registrado de cenários pareados | A estratégia não pode alegar otimização robusta sobre cenários que não observa nem pode consultar previsões futuras; acesso a conjunto de cenários/saídas de simulação para decisão é interface pendente |
| `balanced_tradeoff` | Trade-offs multidimensionais | Escolher considerando o vetor de objetivos e restrições declarados, sem supor pesos universais | Pesos, preferências ou critério de desempate precisam ser publicados |
| `no_action` | Referência sem novas intervenções | Não propor novas ações; manter o funcionamento definido pelo modelo base | A própria evolução exógena/modelada continua; não congelar a cidade |
| `fixed_rule` | Referência determinística simples | Aplicar uma regra pública e imutável sobre um indicador documentado e elegibilidade de ações | Só pode ser finalizada quando métrica granular, alvos e ação compatível existirem |

As cinco políticas de estratégia podem ser regras transparentes no MVP. Não há requisito inicial para LLM, aprendizado por reforço, rede neural ou PyTorch. Uma técnica mais complexa só entra se uma necessidade de política estiver definida e houver comparação demonstrável com as referências sob o mesmo contrato, orçamento computacional, dados e protocolo. O formato de execução deve permitir política determinística interna primeiro; código fornecido por usuários é fora do escopo da v1.

### Política de referência determinística

A regra de referência deve ser simples, legível e reexecutável. Proposta: ordenar alvos elegíveis pelo maior valor de um indicador de problema previsto no protocolo (por exemplo, fila ou atraso), desempatar por identificador estável e propor a ação permitida de menor custo que atenda ao alvo, sem exceder o orçamento discricionário. A regra não pode consultar valores futuros nem adaptar-se a resultados de outras cópias.

Esta definição é **intencionalmente incompleta** para não inventar campos: a implementação atual expõe métricas de mobilidade agregadas da execução, e os contratos de ação/estado estratégico ainda não especificam necessariamente fila por alvo, custo por ação ou mapeamento entre indicador e ação. Até esses contratos existirem, `fixed_rule` é uma referência planejada, não uma política executável. O critério de prioridade, a ação e os desempates devem ser congelados antes de qualquer avaliação.

## 4. Contrato lógico de observação e proposta

O contrato de transporte deve ser versionado e serializável. O envelope conceitual proposto é:

```text
Observation → AgentPolicy → ActionProposal
```

A observação contém somente referências e valores liberados pelo protocolo da partida: identidade e versão do experimento/participante/replicação/rodada; snapshot observado e sua proveniência; relógio/período da decisão; estado derivado permitido; cenário conhecido; orçamento disponível segundo regra publicada; catálogo de ações permitidas e suas restrições documentadas; e resultados de rodadas anteriores que o protocolo autorize. Esses itens são **categorias de informação**, não nomes de campos aprovados. O schema concreto e seus campos dependem das interfaces pendentes de cidade, rodada, indicadores e ações.

A observação deve:

- ser somente leitura e derivada do estado da cópia daquele participante;
- aplicar o mesmo filtro de informação a todos os agentes da mesma classe;
- distinguir fatos configurados, estimados, sintéticos e resultados simulados;
- expor unidades, cobertura temporal/espacial, validade e incerteza dos indicadores fornecidos;
- não incluir dados futuros, estados de outras cópias, segredos, instruções administrativas ou resultados ainda não disponíveis;
- permanecer reproduzível a partir do manifesto do experimento.

A proposta é uma solicitação, nunca uma mutação. Conceitualmente contém versão do schema e do agente, identificador de chamada/rodada, zero ou mais ações tipadas, alvos e parâmetros definidos pelo catálogo de ações, e justificativa opcional curta. A forma final precisa apontar apenas para tipos, unidades e alvos conhecidos. Agente não define custo, prioridade de árbitro, efeito, regra, métrica nem valor de orçamento; valores alegados nesses tópicos não são autoridade e devem ser ignorados ou rejeitados.

Resposta inválida, incompleta, schema desconhecido, tipo/alvo não autorizado ou parâmetro fora de faixa não deve alterar estado. O árbitro valida a proposta e registra separadamente pedido, decisões de validação, custo calculado e resultado aplicado. Rejeição de uma ação não autoriza o runtime a corrigir o estado ou efetivar outra ação implicitamente.

**Interfaces pendentes:** shape de observação, schema de proposta, taxonomia e parâmetros das ações, semântica de “nenhuma ação”, conflitos e atomicidade por rodada. Não reutilizar como contrato de Arena o JSON da simulação de mobilidade: ele representa uma execução de janela e não especifica decisão estratégica entre rodadas.

## 5. Autonomia, autoridade e restrições invioláveis

O agente pode escolher entre ações publicadas, em alvos elegíveis e dentro do orçamento observado. Pode usar apenas histórico da própria cópia entregue pelo runtime e memória interna volátil da sua instância, se memória for habilitada e registrada no protocolo. A proposta v1 recomenda política sem aprendizado durante a competição; se for habilitado estado adaptativo, todo estado interno mutável precisa ser isolado por cópia, versionado ou persistido no manifesto e permitido igualmente a todos.

O agente não pode:

- escrever no snapshot, banco, arquivos da cidade ou artefatos de outra política;
- chamar diretamente simuladores/modelos, API administrativa, shell ou rede externa;
- alterar regras, objetivos, pesos, custos, limites, semente ou relógio;
- ler o futuro, resultados de replicações ainda não concluídas ou detalhes de políticas rivais;
- solicitar gasto acima do saldo discricionário ou comprometer reserva/operação fixa;
- introduzir ações, alvos, unidades ou métricas fora dos schemas publicados;
- tornar aceitável uma violação rígida em troca de benefício em outro indicador.

Restrições rígidas definidas pelo experimento — incluindo equilíbrio orçamentário, reserva protegida, áreas protegidas, capacidade física, segurança e regras de autoridade que venham a ser especificadas — são gates do árbitro, nunca objetivos compensáveis. Os exemplos de temas são princípios da arquitetura; limites concretos e ações aplicáveis dependem do catálogo e das regras versionadas.

O servidor/árbitro é a autoridade sobre validação, ordem de conflitos, custo, transição do estado, falha e métricas. O agente recomenda; não executa.

## 6. Cópias, execução isolada e ciclo decisório

Para cada combinação de política, cenário e replicação, criar uma cópia independente do mesmo snapshot canônico de Aurora. O benchmark pode definir um conjunto pré-registrado de cenários; cada cenário/seed é executado como comparação pareada entre as políticas, mantendo estado, histórico e artefatos privados por execução. `resilience` pode aplicar sua regra ao cenário adverso identificado e sua avaliação agrega o conjunto definido antes da partida. Uma política que precise comparar cenários simultaneamente ou observar resultados de simulações contrafactuais só poderá fazê-lo após um contrato explícito de observação/consulta, hoje pendente. Repetir uma política em outra replicação também cria instância nova; não carregar memória de uma execução para outra salvo protocolo de aprendizado explicitamente separado.

Ciclo proposto por rodada:

1. Materializar estado da cópia, cenário comum e observação permitida.
2. Iniciar a política congelada em sandbox sem acesso de escrita ao estado ou rede.
3. Receber uma proposta até o limite de tempo/tamanho configurado.
4. Validar contra schema, autoridade, precondições, orçamento e restrições invioláveis.
5. Resolver conflitos conforme regra congelada; registrar rejeições e ações efetivas.
6. Avançar modelos urbanos; confirmar a transição somente se modelos e invariantes terminarem com sucesso.
7. Calcular e registrar indicadores; produzir a observação seguinte da mesma cópia.

Falha do agente não interrompe nem altera outras cópias. Falha do modelo ou violação de invariante invalida a execução afetada e impede publicação de resultado parcial como sucesso. A política de continuidade da partida após ausência de proposta deve ser decidida e publicada; proposta padrão: registrar `no_action` naquela rodada e marcar a falha da política, sem penalidade numérica inventada. A execução continua apenas se a pergunta experimental aceitar esse tratamento; comparações que dependam de execução completa devem reportar a política como falha e não ranqueá-la como se tivesse completado o horizonte.

Para agentes internos confiáveis, processo isolado e limites de recursos são recomendados desde o MVP. Se futuramente houver código de terceiros, exigir sandbox mais forte, negar rede e segredos, restringir filesystem, aplicar limites do sistema operacional e revisar o modelo de ameaça; container isolado por si só não prova contenção contra código adversarial.

## 7. Versão congelada, seeds e reprodutibilidade

Antes de executar a primeira replicação, congelar um manifesto imutável contendo ao menos as referências e hashes de: snapshot inicial/configuração; cenário; modelos e adaptadores; catálogo e regras de ações; objetivos, restrições e protocolo de avaliação; artefato/código, parâmetros e instruções de cada política; versões do runtime e dependências; limites de recursos; sementes; e versão dos schemas. Os campos exatos do manifesto da Arena dependem do contrato de experimento ainda pendente.

Uma partida não atualiza agente nem configuração entre rodadas. Correção de política gera nova versão e novo experimento. Aprendizado entre rodadas ou replicações exige protocolo separado, divulgado e igual em oportunidade e limites; avaliação reservada não pode virar dado de ajuste silenciosamente.

Sementes devem ser registradas e separadas por finalidade (geração do snapshot/demanda, cenário externo, componentes estocásticos dos modelos e política, quando aplicável). Derivar sub-sementes de modo determinístico de um identificador mestre e de escopos nomeados reduz colisões e permite repetir componentes sem alterar os demais. As cinco políticas e referências enfrentam a mesma sequência exógena em cada replicação pareada; se o consumo de aleatoriedade de um modelo depender de decisões, usar fluxos separados por finalidade para reduzir acoplamento acidental. A semente não torna determinística uma dependência não determinística: versão de motor, sistema e paralelismo também devem ser registrados, e diferenças residuais devem ser relatadas.

A configuração atual contém semente 42 para a aleatoriedade operacional do SUMO e marca fluxos OD fixos; isso sustenta repetição de execuções atuais, não define por si só o plano de seeds da Arena.

## 8. Orçamento e recursos computacionais

Aurora define economia de jogo em créditos simulados: 100 CS por rodada, com 60 para operação fixa, 10 de reserva e 30 discricionários. Não há conversão para reais. O árbitro deve calcular custo pontual e recorrente pelo catálogo de ações; o agente não fornece custo autoritativo. Ações recorrentes comprometem orçamento futuro conforme regra que ainda precisa ser especificada. Até essa regra existir, só se pode afirmar o limite configurado de orçamento discricionário; não se deve presumir transferência de saldo, crédito, dívida, receita futura ou uso da reserva.

Equidade de execução exige limites iguais para cada participante em CPU, memória, duração da chamada, tamanho de entrada/saída, número máximo de ações e, se aplicável, chamadas/iterações. Os valores numéricos e a política de cobrança/contagem são decisão de configuração do experimento, ainda pendente. Registre consumo observado e limite aplicado. Não usar tokens como unidade universal: só registrar esse limite para políticas cujo runtime realmente tenha tokens.

Limites do simulador (como escoamento e timeout SUMO) são distintos dos limites da política decisora e precisam de valores próprios por componente.

## 9. Timeout e tratamento de falhas

O protocolo deve distinguir pelo menos: timeout, processo encerrado, erro interno, saída malformada, schema incompatível, ação rejeitada, falha de sandbox, falha de modelo e violação de invariante. Registrar estágio, código estável, mensagem sanitizada e se houve proposta recebida. Não expor segredos ou stack traces internos ao agente ou usuário sem política definida.

Timeout não amplia o orçamento nem permite reutilizar uma resposta antiga. O runtime encerra a chamada, preserva a cópia sem mutação e aplica o tratamento de rodada definido no protocolo. Falha do agente deve permanecer ligada àquela política/replicação; não deve cancelar ou contaminar execuções irmãs. Falha de modelo/invariante invalida os resultados científicos da execução afetada e não deve produzir métricas parciais como válidas.

Durações, número de retries (proposta: zero para decisões, para evitar vantagem por repetição), cancelamento e condição de validade/continuidade são parâmetros a congelar antes do benchmark. Um retry técnico só é aceitável se garantir que nenhuma proposta foi aplicada e que usa a mesma entrada, versão, seed e limite total contabilizado.

## 10. Auditoria e proveniência

Para cada decisão, guardar evento encadeado ao experimento, participante, replicação, rodada e hash de observação: versão da política; instante e duração; status de execução; hash/bytes da proposta recebida; validações e regras acionadas; custo calculado; conflitos e desempates; conjunto aplicado; transição/resultados dos modelos; e métricas produzidas. Registrar também hash e manifesto de arquivos de entrada/saída relevantes. A justificativa textual é explicação declarada pelo agente, não prova causal do resultado.

A auditoria deve permitir reconstruir a sequência sem gravar acesso fora do escopo. Observações e resultados carregam classificação de proveniência. Dados pessoais não são necessários para Aurora sintética; se outro cenário incluir mobilidade real, aplicar minimização, controle de acesso e retenção apropriada conforme governança da Arena.

Retenção, formato do log, assinatura/hash-chain, permissões de leitura e mecanismo de cancelamento são decisões de implementação pendentes. Nenhum log de política deve aceitar reescrita silenciosa após o início da avaliação.

## 11. Avaliação multidimensional e protocolo estatístico

A unidade de comparação é uma política executada em uma replicação e cenário pareados. Relatar resultados por rodada e horizonte, bem como distribuição entre replicações. O painel mínimo deve separar:

- mobilidade: tempos/atrasos, viagens concluídas e filas nas janelas realmente modeladas;
- finanças: despesa, compromissos recorrentes, reserva e saldo, quando houver modelo financeiro operacional;
- acesso e equidade: acesso por território/grupo e disparidade, quando cobertura e indicadores estiverem definidos;
- serviços e habitação: cobertura, capacidade, disponibilidade e custo, somente após implementação/validação desses domínios;
- ambiente e resiliência: emissões estimadas, exposição ou desempenho em cenários adversos quando medidos;
- conformidade: violações, rejeições, ações inviáveis e falhas de execução;
- operação da política: tempo/recursos consumidos e completude de decisões.

No MVP executável atual, mobilidade sintética dispõe de métricas de janela e rastreabilidade de seed/versão. As demais dimensões acima são metas do painel ou estão condicionadas a modelos e contratos ainda pendentes. Não fabricar valores ausentes nem tratar métrica de simulação como observação real.

Apresentação padrão: vetor de indicadores com unidade, direção, cobertura, incerteza e desagregação sustentada pelos dados; evolução no tempo; taxas de falha/conformidade; e fronteira de Pareto quando houver múltiplos objetivos comparáveis. Restrições rígidas são exibidas separadamente. Uma pontuação agregada é opcional apenas se pesos, normalização, tratamento de ausência e análise de sensibilidade forem declarados antes da execução; não há pontuação ou vencedor universal na v1.

Cinco agentes são **cinco políticas candidatas**, não cinco amostras estatísticas. Para inferir diferenças, repetir cada política em várias seeds/cenários pareados. Definir o número de replicações após piloto de variabilidade e diferença mínima de interesse, com protocolo e método de incerteza pré-registrados. Reportar estimativas e intervalos/distribuições, diferenças pareadas, taxa de falha e cobertura; não declarar superioridade com base em execuções únicas ou diferenças menores que a variação esperada. Sementes de desenvolvimento e avaliação devem ser separadas; um benchmark reservado reduz ajuste oportunista.

## 12. Decisões necessárias para tornar v1 executável

1. Congelar schemas versionados para observação de decisão estratégica, proposta, resultado do árbitro e estado de rodada.
2. Aprovar catálogo inicial de ações, parâmetros, alvos, custos pontuais/recorrentes, atrasos e pré-condições.
3. Definir regra de conflitos e atomicidade: transação do conjunto, por ação ou outra semântica determinística.
4. Definir observabilidade: métricas, granularidade, atraso de divulgação e informação comum a todas as políticas.
5. Completar política `fixed_rule` com indicadores/alvos/ação existentes no contrato executável.
6. Definir orçamento entre rodadas, saldo não utilizado, reserva, despesas recorrentes e comportamento diante de insuficiência futura.
7. Fixar limites de sandbox, payload, número de ações, CPU/memória e timeouts por chamada/modelo.
8. Definir se falha de agente resulta em rodada vazia, execução inválida ou outra regra; e quando retries são permitidos.
9. Definir se observação de decisão inclui apenas o cenário atual ou informação sobre um conjunto de cenários, e se haverá avaliação contrafactual para política robusta.
10. Escolher indicadores de equidade, grupos/territórios e restrições rígidas do benchmark, sem converter referência de indicadores em pesos implícitos.
11. Definir plano de replicações a partir da variabilidade e do efeito mínimo de interesse.

Até esses itens serem aprovados e implementados, esta especificação orienta desenho e revisão, mas não deve ser interpretada como schema de API pronto nem como autorização para alegar benchmark estatístico completo.

## 13. Referências internas

- [Conceito e princípios da Arena](../conceito/urban-twin-arena.md)
- [Arquitetura completa de referência](../arquitetura/arquitetura-completa-urban-twin-arena.md)
- [Cidade sintética Aurora](../arquitetura/cidade-sintetica-urban-twin-arena.md)
- [`aurora-base-v1.yaml`](../../configs/cities/aurora-base-v1.yaml)
- [Ficha de validação com trânsito observado](../piloto/ficha-piloto.md)
