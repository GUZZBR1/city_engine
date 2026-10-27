# Relatório de validação empírica — TIRTL West Gate Bridge

**Versão:** 0.3 — harness de avaliação e auditoria de mapping, 2026-10-27

**Resultado:** nenhuma baseline SUMO foi executada; não há calibração nem validação held-out.

**Decisão:** parar antes de qualquer comparação com SUMO; limitar os sites 504/505 a profiling descritivo das observações de origem.

## 1. Fonte e cobertura

Fonte: Department of Transport and Planning (DTP), [TIRTL Traffic Counts and Classification](https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts), sob CC BY 4.0. O DTP descreve sensores ópticos que contam e classificam veículos e medem velocidade em bins de 15 minutos por site, heading, classe Austroads e faixa de velocidade. A página atual informa período de reporte de 1/11/2025 a 26/10/2026, atualização em 27/10/2026 e alerta para erros de classificação em alto fluxo e indisponibilidade/desativação por site.

O ZIP de outubro de 2026 auditado contém dados do site 505 entre 1/10 e 26/10. O adapter produziu 2.501 agrupamentos site/horário/heading, 2.492 com heading `W` e 9 com `E`, somando 2.460.308 detecções. Há quatro horários sem observação `W` na grade teórica de 26×96. Ausência não foi convertida em zero. Timestamps permanecem sem fuso porque a fonte não o declara.

## 2. Detector → rede

O [registro de mapping versionado](victoria-tirtl-mapping-register.json) contém os dois detectores examinados, coordenadas de origem, vias candidatas, distâncias exploratórias, método, confiança, ambiguidades e justificativa.

| Detector | Candidato | Confiança | Uso principal |
|---|---|---|---|
| 504 EB | OSM ways 197882461 / 389828674 | `unresolved` | Profiling descritivo; sem comparação espacial |
| 505 WB | OSM way 389828674 | `unresolved` (via candidata) | Profiling descritivo; sem comparação com SUMO |

O dicionário de sites não declara CRS, datum ou precisão das coordenadas. Também não há diagrama de instalação, faixa atendida ou semântica documentada de `heading`. Para o site 505, rótulo WB e predominância de `W` não foram estabelecidos como pistas independentes; a distância exploratória pressupõe um CRS não confirmado e não tem parâmetros reproduzíveis. Não há base para confiança acima de `unresolved`. Os dois sites podem ser usados somente para profiling descritivo dos próprios registros. Não há autorização para comparação observado-versus-simulado nem espacial com SUMO. Não existe correspondência detector→faixa. Nenhum mapping atende ao gate de validação principal.

## 3. SUMO baseline

**Status: não executada; métricas não calculadas.** O repositório não contém rede SUMO de West Gate Bridge, configuração ou rotas para Melbourne. O SUMO atual compila a rede sintética Aurora e calcula métricas agregadas de viagem/fila; não produz contagens e velocidades por detector, segmento e janela alinhadas ao TIRTL. No ambiente desta execução não foram encontrados `sumo`, `netconvert`, Docker ou Podman.

Mesmo com executáveis instalados, os dados TIRTL são contagens pontuais, não matriz OD, rotas nem demanda de entrada. Construir demanda usando a mesma observação que será avaliada criaria circularidade. Portanto, não há comparação observado-vs-simulado defensável a reportar.

| Métrica solicitada | Baseline | Calibrado no treino | Held-out |
|---|---:|---:|---:|
| MAE / RMSE / bias de volume | Não calculado | Não executado | Não executado |
| GEH por bin/detector/segmento (taxa horária equivalente) | Não calculado | Não executado | Não executado |
| MAE / RMSE de velocidade | Não calculado | Não executado | Não executado |
| Erro temporal/resíduos | Não calculado | Não executado | Não executado |

O harness calcula MAE, RMSE e bias em veículos efetivamente contados por intervalo. Para GEH, converte ambos os volumes do intervalo para taxas horárias equivalentes (`contagem × 3600 / duração_em_segundos`) antes de aplicar `sqrt(2*(M−C)^2/(M+C))`; se ambas as taxas forem zero, GEH é zero. A média reportada de GEH é a média não ponderada dos bins pareados. As métricas agrupadas por segmento/janela resumem as linhas pareadas e não somam detectores; totais de corredor exigem uma política de agregação validada. Nenhuma métrica foi calculada nesta auditoria. MAPE não será usado em bins de volume zero ou perto de zero.

## 4. Protocolo e calibração

Não foi congelado um protocolo de calibração nem escolhido calibration/held-out set. A calibração não começou. Fixar split, demanda, parâmetros e thresholds sem uma rede local válida, um mapping aceito e uma definição não circular de demanda daria aparência de rigor sem tornar o experimento identificável.

Antes da próxima tentativa, o protocolo deve registrar em versão imutável: mapping confirmado, rede e checksums; período e timezone; política para classes 13/14, bin aberto `150+` e lacunas; definição independente da demanda; unidade/alinhamento por intervalo; split temporal contíguo; seeds e versões; limites de cada parâmetro; orçamento e regra de parada. A validação deve usar dias posteriores não usados em ajustes. Não se deve mudar o protocolo após observar métricas sem gerar nova versão do experimento.

## 5. Respostas científicas

- **O SUMO reproduz utilmente os dados reais?** Ainda não testado.
- **Onde erra mais?** Não é possível determinar sem uma execução e medições alinhadas.
- **A calibração melhorou? Generalizou?** Não houve calibração ou held-out.
- **Quais detectores ficaram ruins?** Nenhum foi avaliado; 504 e 505 permanecem unresolved.
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
