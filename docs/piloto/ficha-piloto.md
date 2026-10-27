# Ficha do piloto — Gêmeo Digital Urbano

**Status:** rascunho inicial

**Versão:** 0.1

**Caso de uso escolhido:** reproduzir o trânsito observado

## 1. Propósito

Construir uma simulação de uma área urbana limitada e comparar seus resultados com observações reais de trânsito, para entender em quais vias, horários e métricas o modelo representa a realidade com qualidade suficiente.

O piloto começa como uma avaliação de linha de base. Não inclui intervenções viárias nem previsão operacional.

## 2. Decisão que o piloto deve apoiar

**Pergunta de decisão:** a representação da rede e da demanda reproduz o trânsito observado na área e no período selecionados com precisão adequada para, em uma fase posterior, avaliar cenários?

**Responsável pela avaliação:** a definir.

## 3. Recorte geográfico e temporal

| Campo | Definição |
|---|---|
| Cidade | A definir |
| Bairro, corredor ou conjunto de cruzamentos | A definir |
| Limites geográficos | A definir |
| Dia(s) representativo(s) | A definir |
| Período do dia | A definir |
| Intervalo de agregação dos dados | A definir conforme as fontes disponíveis |

O recorte deve ser pequeno o suficiente para revisão manual da rede e conter observações que permitam comparar a simulação com o trânsito real.

## 4. Usuários e participantes

| Papel | Responsabilidade | Pessoa ou organização |
|---|---|---|
| Especialista de tráfego | Revisar a rede, as premissas e os resultados | A definir |
| Responsável pelos dados | Confirmar acesso, licença, qualidade e cobertura | A definir |
| Responsável pela validação | Aprovar protocolo e critérios de avaliação | A definir |
| Usuários dos resultados | Interpretar o relatório do piloto | A definir |

## 5. Dados necessários

| Dado | Uso | Fonte e responsável | Período e cobertura | Licença/base de uso | Estado |
|---|---|---|---|---|---|
| Rede viária e geometrias | Construir o modelo da área | OpenStreetMap e/ou fonte local; confirmar | A definir | Confirmar atribuição e condições de uso | Pendente |
| Contagens ou volumes de veículos | Estimar e comparar fluxos | A definir | A definir | A definir | Pendente |
| Velocidades ou tempos de percurso | Calibrar e avaliar deslocamentos | A definir | A definir | A definir | Pendente |
| Filas ou ocupação, se disponíveis | Avaliar congestionamento local | A definir | A definir | A definir | Opcional |
| Planos e tempos semafóricos, se disponíveis | Representar controles existentes | A definir | A definir | A definir | Pendente |

Para cada fonte, registrar origem, responsável, licença, método de coleta, resolução temporal e espacial, período de validade, limitações e transformações aplicadas. Dados pessoais de mobilidade não devem ser incorporados sem análise de finalidade, base legal, minimização e retenção.

## 6. Método de avaliação

1. Importar e revisar a rede; registrar campos ausentes, correções e incertezas.
2. Definir a demanda e os parâmetros usando apenas os dados destinados à calibração.
3. Reservar dados independentes — por período, local ou ambos — para validação, antes de ajustar o modelo.
4. Executar a simulação com rede, dados, parâmetros, versão do SUMO e sementes registrados.
5. Comparar observado e simulado por trecho, horário e métrica, incluindo limitações e incerteza.

Os critérios numéricos de aprovação serão definidos após confirmar quais dados estão disponíveis e sua qualidade. GEH pode ser usado para volumes; MAE/RMSE para velocidades ou tempos; e métricas específicas para filas, se houver observações adequadas. Nenhuma métrica isolada será tratada como prova de validade geral.

## 7. Indicadores

| Indicador | Comparação | Critério de aprovação |
|---|---|---|
| Volume de veículos por trecho e intervalo | Observado vs. simulado | A definir |
| Velocidade por trecho e intervalo | Observada vs. simulada | A definir |
| Tempo de percurso | Observado vs. simulado | A definir |
| Extensão ou duração de filas, quando observável | Observada vs. simulada | A definir |
| Cobertura das observações | Área/horários com dados válidos | A definir |

Os relatórios devem mostrar vieses, dados faltantes, intervalos de incerteza e o domínio efetivamente avaliado. Resultados de uma área ou horário não validam automaticamente outras condições.

## 8. Entregáveis do piloto

- Rede viária versionada, com relatório de qualidade e registro de correções.
- Manifesto de dados com fontes, licenças, cobertura e transformações.
- Configuração reproduzível da simulação e respectiva versão dos artefatos.
- Relatório comparando métricas observadas e simuladas, com limites e incerteza.
- Recomendação fundamentada sobre avançar, corrigir dados/modelo ou restringir o uso.

## 9. Critérios de conclusão

- A área e o período do piloto estão delimitados e revisados por especialista local.
- Fontes, permissões de uso e limitações dos dados estão documentadas.
- Dados usados na calibração estão separados dos dados usados na validação.
- A execução pode ser reproduzida a partir de entradas, versões e sementes registradas.
- As métricas e critérios de aprovação foram definidos antes da validação final.
- A conclusão declara explicitamente o que foi validado e o que permanece sem evidência.

Se não houver observações independentes suficientes, o piloto poderá demonstrar a cadeia técnica de importação e simulação, mas os resultados deverão ser rotulados como exploratórios, sem alegação de validação do trânsito real.

## 10. Fora do escopo desta etapa

- Comparação ou otimização automática de intervenções.
- Previsão operacional em tempo real.
- Escrita ou controle de semáforos e equipamentos reais.
- Validação de uma cidade inteira a partir de um recorte limitado.
- Kubernetes, processamento distribuído de uma única simulação ou adoção antecipada de componentes de infraestrutura sem necessidade medida.

## 11. Riscos e respostas

| Risco | Resposta prevista |
|---|---|
| Rede OSM incompleta ou incorreta | Revisão local, relatório de lacunas e distinção entre desconhecido e inexistente confirmado |
| Dados sem cobertura ou licença adequada | Confirmar acesso e condições antes de fixar o recorte; restringir ou interromper alegações de validade se necessário |
| Demanda não identificável com as observações disponíveis | Documentar hipóteses e limitações; não apresentar demanda sintética como medida real |
| Resultado varia entre execuções | Rodar sementes distintas e reportar variabilidade, além de registrar a semente de cada execução |
| Efeito de rede fora da área simulada | Delimitar claramente fronteiras e não extrapolar conclusões além da cobertura modelada |

## 12. Próximas informações a preencher

1. Cidade e área candidata.
2. Fontes de contagens, velocidades ou tempos de percurso e respectivos responsáveis.
3. Período que essas observações cobrem.
4. Pessoa ou equipe que revisará a rede e aprovará o protocolo de validação.
5. Critérios de erro aceitável para o uso pretendido.
