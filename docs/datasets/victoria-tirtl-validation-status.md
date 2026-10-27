# Relatório de validação empírica — TIRTL West Gate Bridge

**Versão:** 0.1 — auditoria de bloqueios, 2026-10-27

**Resultado:** nenhuma baseline SUMO foi executada; não há calibração nem validação held-out.

**Harness:** `packages/traffic_observations/traffic_observations/evaluation.py`
agora contém comparação reutilizável de volume/velocidade por intervalo,
resíduos agrupados e manifesto hashado. Nenhum artefato de avaliação foi
gerado: métricas de baseline, treino e holdout permanecem unset. Os testes usam
somente linhas artificiais e não são resultados de tráfego.

**Decisão:** parar antes da validação principal; preservar o site 505 apenas para exploração.

## 1. Fonte e cobertura

Fonte: Department of Transport and Planning (DTP), [TIRTL Traffic Counts and Classification](https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts), sob CC BY 4.0. O DTP descreve sensores ópticos que contam e classificam veículos e medem velocidade em bins de 15 minutos por site, heading, classe Austroads e faixa de velocidade. A página atual informa período de reporte de 1/11/2025 a 26/10/2026, atualização em 27/10/2026 e alerta para erros de classificação em alto fluxo e indisponibilidade/desativação por site.

O ZIP de outubro de 2026 auditado contém dados do site 505 entre 1/10 e 26/10. O adapter produziu 2.501 agrupamentos site/horário/heading, 2.492 com heading `W` e 9 com `E`, somando 2.460.308 detecções. Há quatro horários sem observação `W` na grade teórica de 26×96. Ausência não foi convertida em zero. Timestamps permanecem sem fuso porque a fonte não o declara.

## 2. Detector → rede

O [registro de mapping versionado](victoria-tirtl-mapping-register.json) contém os dois detectores examinados, coordenadas de origem, vias candidatas, distâncias exploratórias, método, confiança, ambiguidades e justificativa.

| Detector | Candidato | Confiança | Uso principal |
|---|---|---|---|
| 504 EB | OSM ways 197882461 / 389828674 | `unresolved` | Excluído |
| 505 WB | OSM way 389828674 | `medium_confidence` | Exploração somente; excluído |

O dicionário de sites não declara CRS, datum ou precisão das coordenadas. Também não há diagrama de instalação, faixa atendida ou semântica documentada de `heading`. O 505 é favorecido pelo rótulo WB, predominância de `W` e distância exploratória, mas esses dados não confirmam o trecho físico. Não existe correspondência detector→faixa. Nenhum mapping atende ao gate de validação principal.

## 3. SUMO baseline

**Status: não executada; métricas não calculadas.** O repositório não contém rede SUMO de West Gate Bridge, configuração ou rotas para Melbourne. O SUMO atual compila a rede sintética Aurora e calcula métricas agregadas de viagem/fila; não produz contagens e velocidades por detector, segmento e janela alinhadas ao TIRTL. No ambiente desta execução não foram encontrados `sumo`, `netconvert`, Docker ou Podman.

Mesmo com executáveis instalados, os dados TIRTL são contagens pontuais, não matriz OD, rotas nem demanda de entrada. Construir demanda usando a mesma observação que será avaliada criaria circularidade. Portanto, não há comparação observado-vs-simulado defensável a reportar.

Os bloqueios técnicos atuais são: (1) nenhum mapping detector→faixa foi confirmado; (2) não existe uma rede SUMO West Gate verificada no checkout; (3) não há série de saídas SUMO por detector/segmento/janela; (4) falta uma definição de demanda de fronteira independente das contagens usadas como alvo; e (5) SUMO/netconvert não estavam disponíveis na auditoria registrada acima. A implementação do harness não resolve esses bloqueios e não produziu números.

| Métrica solicitada | Baseline | Calibrado no treino | Held-out |
|---|---:|---:|---:|
| MAE / RMSE / bias de volume | Não calculado | Não executado | Não executado |
| GEH por bin/detector/segmento | Não calculado | Não executado | Não executado |
| MAE / RMSE de velocidade | Não calculado | Não executado | Não executado |
| Erro temporal/resíduos | Não calculado | Não executado | Não executado |

As fórmulas planejadas são: MAE = média de `|simulado − observado|`; RMSE = raiz da média do erro ao quadrado; bias = média de `simulado − observado`; GEH por volume comparável = `sqrt(2*(M−C)^2/(M+C))`, indefinido quando ambos são zero. MAPE não será usado em bins de volume zero ou perto de zero.

## 4. Protocolo e calibração

Não foi congelado um protocolo de calibração e nenhum split foi escolhido. A calibração não começou. Fixar demanda, parâmetros e thresholds sem uma rede local válida, um mapping aceito e uma definição não circular de demanda não tornaria o experimento identificável.

Para a execução futura, registrar a partição antes de examinar resultados: um período de calibração contíguo e um período posterior, temporalmente independente, como holdout intocado. Se houver cobertura, reservar também segmento/corredor espacial independente. As fronteiras devem ser atribuídas usando timestamps, IDs estáveis de segmento e metadados de cobertura, sem inspecionar valores de erro, pontuar splits candidatos ou ajustar parâmetros. Congelar split, mapping, política de medição, demanda independente, limites de parâmetros, seeds e checksums da rede antes do ajuste. Exploração de dados fica limitada a schema, timezone, cobertura, proveniência e qualidade necessária para interpretar os arquivos; registrar qualquer limitação e não usar resultados exploratórios para escolher split.

Antes da próxima tentativa, o protocolo deve registrar em versão imutável: mapping confirmado, rede e checksums; período e timezone; política para classes 13/14, bin aberto `150+` e lacunas; definição independente da demanda; unidade/alinhamento por intervalo; split temporal contíguo; seeds e versões; limites de cada parâmetro; orçamento e regra de parada. A validação deve usar dias posteriores não usados em ajustes. Não se deve mudar o protocolo após observar métricas sem gerar nova versão do experimento.

## 5. Respostas científicas

- **O SUMO reproduz utilmente os dados reais?** Ainda não testado.
- **Onde erra mais?** Não é possível determinar sem uma execução e medições alinhadas.
- **A calibração melhorou? Generalizou?** Não houve calibração ou held-out.
- **Quais detectores ficaram ruins?** Nenhum foi avaliado; 504 está unresolved e 505 é apenas candidato médio.
- **Quais hipóteses estão sem sustentação?** CRS/precisão das coordenadas, detector→via/faixa, significado dos headings, demanda/OD de fronteira e compatibilidade da velocidade agregada.
- **Módulo empiricamente validado como gêmeo digital?** Não. Há fonte observada documentada e adapter; faltam mapping confiável, rede SUMO real, comparação, calibração e validação independente.

## 6. Reprodutibilidade e próximos gates

O [documento do piloto](victoria-tirtl-pilot.md) registra checksums dos arquivos locais, sem versionar os dados brutos. A suite PostGIS real está separada em `apps/api/tests/integration/test_postgis_integration.py` e exige `CITY_ENGINE_TEST_DATABASE_URL`; ela não foi executada neste ambiente. A suíte unitária valida apenas a lógica do repositório com pool falso.

1. Obter do DTP CRS/precisão, plano de instalação e definição de heading para 504/505; promover apenas mappings demonstrados.
2. Construir e versionar rede SUMO de West Gate com acessos e limites de demanda documentados.
3. Definir demanda de fronteira sem reutilizar as observações do detector como verdade-alvo.
4. Gerar medidas SUMO por detector/segmento em bins de 15 minutos; validar unidades e sentidos.
5. Só então congelar split e protocolo, executar baseline, calibrar no treino e avaliar uma janela posterior held-out.
6. Executar as migrations e integração em PostgreSQL/PostGIS descartável e registrar versão do servidor, extensão e resultados.
