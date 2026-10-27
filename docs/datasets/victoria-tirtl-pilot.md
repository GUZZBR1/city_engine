# Piloto empírico de tráfego: TIRTL, Victoria

**Estado:** aprovado para ingestão e replay histórico; mapeamento para SUMO permanece provisório.
**Região candidata:** West Gate Bridge, Melbourne, Victoria, Austrália.
**Site inicial:** 505 — “M1 West Gate Bridge Outbound (WB)”.
**Janela local auditada:** arquivo mensal de outubro de 2026. O portal oficial informa período de reporte até 26 de outubro de 2026 e atualização em 27 de outubro; a extração do site 505 também chega a 26 de outubro. [Metadados atuais do portal](https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts)

## Fonte e proveniência

- Proprietário: Department of Transport and Planning (DTP), Victoria.
- Fonte: [TIRTL Traffic Counts and Classification](https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts).
- Licença declarada pelo portal oficial: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Preservar crédito ao DTP e indicar alterações/agregações.
- Metodologia publicada: dispositivos Infra-Red Traffic Logger contam e classificam veículos e medem velocidade; o portal descreve a tecnologia como óptica, sem contato. Cada registro agregado representa volume por bin de 15 minutos, site, heading, classe Austroads e bin de velocidade.
- O DTP alerta para erros de classificação em alto fluxo e interrupções ou desativação de dispositivos. A janela válida pode diferir por site.
- Classificação do dado: `observed` para detecções publicadas; `derived` para taxa horária e média aproximada de velocidade produzidas pelo adapter. A publicação não fornece OD, trajetórias, ocupação, fila ou movimento de conversão.

## Artefatos examinados

Os arquivos foram baixados para `data/external/tirtl/`, ignorado pelo Git, e não são distribuídos pelo repositório.

| Artefato | Fonte/versão | SHA-256 | Observações |
|---|---|---|---|
| `october-2026.zip` | Recurso mensal DTP; arquivo de 100,850,482 bytes (ZIP). | `13ca9c2dc7d2ffbe3bdc4eaf4e1d4a6ae86263520765df951b27b71eddf98875` | Contém CSVs diários. O conteúdo do site 505 vai de 01/10 00:00 a 26/10 23:45, consistente com o período de reporte atual do portal (fim em 26/10; atualização em 27/10/2026). |
| `sites.csv` | Recurso oficial TIRTL Sites, 406 registros. | `d588483a42115c3c25aa3d3dd66e6ab05457cde44993156f950c2d1ad254ddb7` | `site`, descrição e coordenadas; usar versão junto com o ZIP. |
| `osm-map.xml` | API OpenStreetMap, bbox local consultada em 2026-10-27. | `56c0496f8dfd62038986c42e99370ece29a13a8f488dbdae8071aba5ceddf1f3` | Extração auxiliar da geometria; OSM é ODbL e requer atribuição. Não é uma rede SUMO. |

O ZIP foi percorrido integralmente para os sites 504 e 505, agregando somente os registros de classe/velocidade presentes; o adapter faz esse filtro em streaming por CSV diário. Para o site 505, o adapter produziu **2.501 observações de intervalos/headings**, cobrindo 26 datas, e somou **2.460.308 detecções** preservando os headings recebidos. Destas observações, 2.492 têm `W` e 9 têm `E`, apesar do rótulo WB. Em uma grade teórica de 26×96 bins de 15 minutos, há quatro timestamps sem `W`; a fonte não permite decidir se cada ausência significa zero ou falha de medição. A tabela de sites fornece campos chamados latitude e longitude, mas o dicionário consultado não informa datum/CRS. O arquivo oficial TIRTL deve ser obtido novamente do portal e seu novo checksum registrado para reproduzir a ingestão.

## Site e mapeamento espacial

O CSV oficial identifica 504 como inbound (EB), coordenadas `-37.830900, 144.900501`, e 505 como outbound (WB), coordenadas `-37.830815, 144.900329`. No mês auditado, o 505 apresenta nove observações `E` além das `W`, e o 504 também apresentou um `W` na amostra independente de 12 de outubro. A direção reportada deve ser preservada; usar o heading como filtro exige política explícita e rastreável.

Uma consulta OSM retornou as vias unidirecionais `West Gate Freeway/M1`, ambas tagged como bridge de cinco faixas: [way 197882461](https://www.openstreetmap.org/way/197882461) e [way 389828674](https://www.openstreetmap.org/way/389828674). A tabela TIRTL não declara CRS; as distâncias abaixo são **inferência exploratória**, calculada interpretando os campos de coordenadas do TIRTL como latitude/longitude geográfica compatível com o OSM. Não use essas distâncias como transformação ou prova de correspondência:

| Site | Distância a way 197882461 | Distância a way 389828674 | Avaliação |
|---|---:|---:|---|
| 504 EB | ~9,3 m | ~8,0 m | Ambíguo por proximidade; a direção favorece 197882461, mas não confirma instalação. |
| 505 WB | ~10,8 m | ~6,5 m | O rótulo WB, heading W e proximidade favorecem 389828674; ainda é associação provisória. |

**Não há evidência pública consultada que identifique faixa, ponto físico de montagem ou tolerância da coordenada.** Portanto:

- Observações mantêm latitude/longitude de origem, `location_id=tirtl-site:<id>` e CRS não especificado; a camada PostGIS não cria geometria EPSG:4326 sem CRS confirmado.
- O adapter não popula `road_segment_id`, `intersection_id`, faixa ou confiança numérica.
- OSM Way não é tratado como edge SUMO. A conversão OSM→SUMO e o vínculo detector→edge precisam ser revisados contra um artefato de rede versionado.
- O site 505 é o piloto mais plausível para seguir investigação, não uma correspondência confirmada. O 504 permanece ambíguo.

## Semântica e qualidade dos dados

- `volume` é contagem durante o intervalo de 15 minutos por classe e speed bin. O adapter soma classes e bins presentes em cada `(date, time_bin, site, heading)` e define `flow_veh_h = volume × 4`; a contagem original fica preservada.
- A fonte não explicita timezone para `date`/`time_bin`; o adapter preserva timestamp ingênuo e registra `timestamp_timezone` como não especificado. Não converter para UTC sem confirmação do DTP.
- Speed bins têm largura de 5 km/h. A média é derivada pela média ponderada dos pontos médios dos bins finitos; `150km/hr +` usa 150 km/h como limite inferior. Observações com bin aberto levam uma flag de limite inferior; essa média não é uma medida exata.
- Classes 13 (erro) e 14 (bicicletas) são mantidas e sinalizadas. Comparação com volume de veículos motorizados exige uma regra explícita de tratamento; não retirar silenciosamente essas classes.
- Linha ausente não é convertida em contagem zero. Pode refletir ausência de tráfego, downtime, exportação ou lacuna; requer diagnóstico da fonte.
- O site 504 mostrou um registro heading W em uma amostra de 12/10, embora a descrição oficial seja EB. Preservar headings separadamente e auditar todas as datas antes de agregação direcional.
- O site 505 apresentou 9 observações `E`, embora o recurso esteja descrito como WB. O portal oficial, consultado em 27/10/2026, também reporta cobertura até 26/10; a janela do arquivo e a metadata atual coincidem. A divergência de heading ainda exige esclarecimento antes de uma alegação de cobertura completa ou validação por sentido.
- A unidade de velocidade e bins em km/h aparece no dicionário oficial; nenhum campo de densidade é publicado.

## Uso recomendado

| Uso | Decisão |
|---|---|
| Catálogo de fonte, provenance e observações históricas | **Sim**, com checksum, licença, versão, timestamps originais e referências preservados. |
| Replay temporal isolado | **Sim**, sem preencher intervalos ausentes. |
| Ingestão e atualização de estado observacional separado de Aurora | **Sim**, após persistência; as coordenadas permanecem sem geometria espacial enquanto o CRS não for confirmado. |
| Perfil de fluxo/velocidade para o site 505 | **Profiling descritivo dos registros de origem somente**; sem comparação com SUMO ou interpretação como medida de um edge até confirmação independente do mapping. |
| OD/demanda da rede | **Não**; contagens pontuais não identificam viagens, origens, destinos ou rotas. |
| Calibração/validação de corredor SUMO | **Ainda não**; requer detector→edge verificado, rede SUMO do local, demanda/rotas documentadas e período held-out. |
| Calibração/validação de Aurora | **Não**; Aurora segue sendo uma cidade sintética em outra geografia e referência espacial. |

## Gate para SUMO

O piloto só pode avançar para uma baseline numérica quando houver: (1) confirmação DTP da cobertura e direção do 505 ou documentação independente de instalação; (2) extração OSM datada com licença/atribuição, compilada e validada para a região relevante; (3) edge SUMO que cruze a seção observada, sem ambiguidade de sentido/faixa; (4) política explícita para classes 13/14, bin `150+`, lacunas e timezone; (5) demanda de entrada definida sem copiar a própria série de validação; (6) janela de validação distinta do período usado para eventual calibração. Sem esses requisitos, reportar dados reais importados e limitação de mapeamento, sem declarar baseline validada, melhoria de calibração ou gêmeo digital empiricamente validado.

## Próxima etapa

Prosseguir com a persistência imutável da fonte/dataset e ingestão do site 505 como observação geográfica sem edge atribuído. Paralelamente, solicitar/obter documentação de instalação do DTP. Só então decidir se a rede local pode sustentar o baseline. O primeiro passo útil é comparar contagens por intervalo e heading, reportando cobertura e gaps, antes de inferir demanda.
