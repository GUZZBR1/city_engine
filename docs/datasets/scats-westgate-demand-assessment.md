# Avaliação delimitada: SCATS no West Gate

**Data da consulta:** 2026-10-27
**Escopo:** somente Open Data Victoria/DTP; nenhuma rota, OD ou simulação SUMO foi criada/executada.
**Decisão binária:** **SCATS cannot currently be used as independent demand constraints for this network.**

## Resultado

Há cobertura espacial SCATS relevante além dos TIRTL 504/505. O DTP publica contagens de loops de tráfego SCATS por site/detector, em bins de 15 minutos, separadamente dos dados TIRTL; e publica um inventário georreferenciado dos sinais. O join reproduzível para localizar sinais é por `SITE_NO` do inventário versus `NB_SCATS_SITE` dos volumes, não por nearest point.

Esse join chega ao **site**, mas os volumes não trazem aproximação, faixa, movimento, rumo ou grupo de sinal. Foi recuperada e inspecionada por leitura HTTP range a operation sheet do site 4901; ela liga números de detector do controlador a aproximações/grupos e mostra um mapa de loops. A folha é datada de 2014, e a documentação DTP consultada não estabelece que esses números sejam a mesma chave de `NB_DETECTOR` nem confirma que a configuração siga vigente em outubro de 2026. Portanto continua sem associação aceita detector→movimento/faixa SUMO para volumes 2026. Contagens pontuais também não definem OD nem rotas.

## Evidência e reprodução

### Fontes oficiais

1. **[Traffic Signal Volume Data (SCATS)](https://opendata.transport.vic.gov.au/dataset/traffic-signal-volume-data)** — DTP declara contagens por loop/detector e site, agregadas em períodos de 15 minutos, fonte SCATS, atualização diária e reporte desde 1 de abril de 2014. A licença é CC BY 4.0. A página alerta para limite/cobertura máxima de 24 volume detectors por site.
2. **[Victorian Traffic Signals](https://opendata.transport.vic.gov.au/dataset/victorian-traffic-signals)** — inventário DTP de sinais em operação, CSV, CC BY 4.0. O recurso declara os campos `SITE_NO` (identificador do site de sinal), `SITE_NAME`, `TYPE`, `MUNICIPALITY`, `LATITUDE`, `LONGITUDE`; sua metadata primária informa `Geographic Coordinate System: WGS84`; cobertura Victoria.
3. **[Traffic Signal Configuration Data Sheets](https://opendata.transport.vic.gov.au/dataset/traffic-signal-configuration-data-sheets)** — DTP descreve folhas operacionais específicas por site, detalhando funções de detectores e signal groups e as fases. Arquivos ZIP são particionados por número de site: [2750–2999](https://opendata.transport.vic.gov.au/dataset/traffic-signal-configuration-data-sheets/resource/128af789-f38d-4b98-819e-2505ab67023b) (ex.: 2880) e [4750–4999](https://opendata.transport.vic.gov.au/dataset/traffic-signal-configuration-data-sheets/resource/60f07908-0abd-419f-aee7-db37607d7f06) (ex.: 4901). O dicionário lista `Site Number`, `Detectors`, `Signal Groups`, `Operation Notes`, `Phasing` e `Time Settings`. A coleção informa atualização ad hoc e período 27/07/2003–16/06/2025; as páginas dos recursos particionados registram metadados de 10/02/2022, o que pede cuidado com a vigência do layout. CC BY 4.0.

### Campos observados nos volumes

O dicionário oficial do [recurso mensal de outubro de 2026](https://opendata.transport.vic.gov.au/dataset/traffic-signal-volume-data/resource/001ace40-280b-462d-b580-7a79e70185fb) lista:

- `NB_SCATS_SITE`: SCATS Site ID;
- `NB_DETECTOR`: SCATS Detector ID;
- `QT_INTERVAL_COUNT`: data de leitura, descrita como fim do intervalo em Australian Eastern Standard Time;
- `V00`…`V95`: volumes em 96 períodos de 15 minutos; `V00` = 00:00–00:15;
- `NM_REGION`, `CT_RECORDS`, `QT_VOLUME_24HOUR`, `CT_ALARM_24HOUR`.

O DTP documenta cada valor de `V00`–`V95` como número de transições de estado do detector de desativado para ativado. **Não equiparar automaticamente essas transições a contagens de veículos ou fluxos independentemente verificados:** isso depende da configuração do loop e do comportamento de detecção, que precisam ser validados para cada site/detector. A série registra a saída do detector, não uma identificação semântica de movimento. A página não documenta direção/faixa por campo. Coordenadas não estão nos registros de volume.

### Verificação local reproduzível

Consultados o inventário e o pacote oficial de outubro de 2026 (recurso reporta 01–26/10/2026; atualização 27/10/2026). Extração testada: `VSDATA_20261001.csv`. O arquivo tem registros diários, com as colunas acima. Para reproduzir cobertura de um site, obtenha os dois recursos no CKAN oficial e faça igualdade exata de IDs:

```python
signals = read_csv("victorian_traffic_signals.csv")
volumes = read_csv("VSDATA_20261001.csv")
signals[signals.SITE_NO == site_id]
volumes[volumes.NB_SCATS_SITE == site_id]
```

Esse join prova que o site enumerado no inventário tem registros de volume naquele dia. Ele **não** prova por si só orientação, localização de cada loop na geometria ou seu movimento. Não se deve substituir isso por proximidade entre pontos.

URLs diretas consultadas:

- Inventário: `https://opendata.transport.vic.gov.au/dataset/923af458-363d-469f-bc5e-84746a80b9a2/resource/1036a318-8867-4dc6-bd84-fc3bcd6cbdb9/download/victorian_traffic_signals.csv`
- Volumes outubro/2026: `https://opendata.transport.vic.gov.au/dataset/331b846b-1e18-415f-a3f3-ce4198d86c82/resource/001ace40-280b-462d-b580-7a79e70185fb/download/traffic_signal_volume_data_october_2026.zip`
- Folhas 2750–2999: `https://opendata.transport.vic.gov.au/dataset/48ec6c0a-994e-4f27-b3b8-bd7ffa86deda/resource/128af789-f38d-4b98-819e-2505ab67023b/download/2750-2999.zip`
- Folhas 4750–4999: `https://opendata.transport.vic.gov.au/dataset/48ec6c0a-994e-4f27-b3b8-bd7ffa86deda/resource/60f07908-0abd-419f-aee7-db37607d7f06/download/4750-4999.zip`

Checksums dos downloads consultados (SHA-256):

| Recurso | SHA-256 |
|---|---|
| `victorian_traffic_signals.csv` | `e5fd0df86f223db345ffbdeb21db188e2240f4eb7409e4998ea5fde0a8a766af` |
| `traffic_signal_volume_data_october_2026.zip` | `aa037fb8f9765ee7692e5cfeb8aa5c226f4185fa5ad5096bf1e76cb190a0a1e7` |

### Cobertura além de TIRTL 504/505

Foi aplicado apenas como **filtro de busca**, não como atribuição de detector, o bbox da extração de rede atual (`lon 144.84–144.95`, `lat -37.86–-37.80`). Inventário: 207 sinais com coordenadas parseáveis nessa caixa. Igualdade exata `SITE_NO == NB_SCATS_SITE` no arquivo do dia 01/10 encontrou volumes em 183 desses sites (inclui interseções e sites de travessia de pedestres; não interpretar todos como movimentos veiculares).

Exemplos materialmente ligados ao entorno rodoviário do West Gate no inventário DTP e com volumes no dia verificado:

| `SITE_NO` = `NB_SCATS_SITE` | `SITE_NAME` do inventário | Tipo | Coordenadas inventário (lat, lon) | `NB_DETECTOR` distintos no dia |
|---:|---|---|---|---:|
| 2880 | WESTGATE FWY/WILLIAMSTOWN | INT | -37.825989, 144.880960 | 32 (IDs 0–31) |
| 2881 | WESTGATE FWY/MILLERS | INT | -37.825310, 144.849091 | 32 (IDs 0–31) |
| 2399 | TODD/WEBB DOCK/WESTGATE WB RAMPS | INT | -37.834093, 144.913483 | 24 (IDs 1–24) |
| 2887 | WILLIAMSTOWN/TODD | INT | -37.836949, 144.914821 | 24 (IDs 1–24) |
| 2896 | PLUMMER/SALMON | INT | -37.832800, 144.924305 | 24 (IDs 1–24) |
| 2897 | PLUMMER/PROHASKY | INT | -37.833789, 144.919211 | 24 (IDs 1–24) |
| 2898 | TODD OFF RAMP/PROHASKY/SERVICE CENTRE | INT | -37.831828, 144.918401 | 24 (IDs 1–24) |
| 4901 | WESTGATE FWY WB/MONTAGUE | INT | -37.826556, 144.945968 | 24 (IDs 1–24) |
| 2886 | WESTGATE FWY EB/LORIMER | INT | -37.825252, 144.946210 | 24 (IDs 1–24) |

Os pontos estão fora da posição/linha de medição TIRTL sobre a ponte segundo os próprios nomes oficiais dos sites; não são novos sensores bridge-wide e não medem necessariamente os mesmos segmentos. Esses exemplos mostram cobertura espacial de sinais à oeste, sul e leste da ponte, independente da medição TIRTL 504/505; não afirmam quais movimentos dos sinais alimentam os contadores.

### Tentativa direcionada de mapping: site 4901

O recurso DTP oficial [Traffic Signal Configuration Data Sheets 4750–4999](https://opendata.transport.vic.gov.au/dataset/traffic-signal-configuration-data-sheets/resource/60f07908-0abd-419f-aee7-db37607d7f06) é um ZIP de 2,37 GB. O servidor aceita `Range`; o diretório central permitiu localizar `4750-4999/4901.htm` e suas páginas incorporadas, obtendo cerca de 3,37 MB de bytes do arquivo compactado em vez do pacote completo. O workbook tem 13 folhas. Seu cabeçalho identifica `WEST GATE FWY / MONTAGUE ST`, site 4901, plan 553671, e data do projeto 30/04/2014. A página 1 ainda lista datas-alvo de draft (05/05/2014) e conclusão do programa (19/05/2014). A entrada do ZIP para o workbook é datada de 05/08/2025; o recurso/arquivo foi atualizado pelo DTP em 20/03/2026. Essas datas de publicação/empacotamento não são uma data de vigência/revisão em 2026.

Os hashes abaixo são SHA-256 dos **bytes descomprimidos** desses membros exatos do ZIP oficial, obtidos com leitura HTTP Range em 27/10/2026. O checksum identifica o conteúdo recuperado, não sua vigência operacional:

| Membro do ZIP | Conteúdo relevante | Bytes | SHA-256 |
|---|---|---:|---|
| `4750-4999/4901.htm` | página índice/capa do workbook | 12.570 | `9a6c82fa0d2a57083d7bb578a3ca452c67aa01b3e8b5ecf7c2d2cb651396998e` |
| `4750-4999/4901_files/sheet002.htm` | Group Allocation / Detector Map | 905.566 | `233ba574e222f37baa31a059b847e07a3ee96a4dac8052dce3fec980c8711abd` |
| `4750-4999/4901_files/sheet003.htm` | Phasing | 419.146 | `e66caf88ca05b27f0d892b5081845d006f68c0a1ea52f0f8a31a4e7852a37346` |
| `4750-4999/4901_files/sheet004.htm` | Detector Functions | 63.565 | `e355137763e0a62f9153429fe6763748dd4bc7ebadc461eb59c46d510eb23c5f` |
| `4750-4999/4901_files/sheet005.htm` | Approach Definitions | 34.258 | `084e23b72ae9fa22dffe658a9aa2704fa5ffd0c10fa8b46c7ae9588a3d3377b4` |
| `4750-4999/4901_files/sheet012.htm` | Operation Notes | 85.965 | `2b94f71524bd037f9fd28f2e6b7aa0d5f42f5f20dff99e936e7fd96d4bb7ca50` |
| `4750-4999/4901_files/image273.gif` | embedded Detector Map diagram | 14.576 | `87ccf4009b59a0bf7c29df99f63b7898392fa63a71a15cbcf59b17f540fd77e1` |

O volume oficial de 01/10/2026 foi também lido por HTTP range da entrada `VSDATA_20261001.csv` no [ZIP mensal de outubro](https://opendata.transport.vic.gov.au/dataset/traffic-signal-volume-data/resource/001ace40-280b-462d-b580-7a79e70185fb): 24 linhas para `NB_SCATS_SITE=4901`, `NB_DETECTOR` exatamente 1–24, e `CT_RECORDS=96` por linha. O SHA-256 do CSV diário extraído foi `6f4b1674259e98d657f5048d76bdbf9eede0da469a2fe264a77abf18f218338c`.

O conteúdo da folha dá evidência de configuração explícita, não uma inferência pela ordem dos IDs:

- Folha “DETECTOR FUNCTIONS”: detectores 1–24 são entradas internas 1–24; 25–32 aparecem como entradas externas. O mapa associado identifica 25–32 como botões de chamada de pedestres e assinala 4 e 9 como queue loops.
- Folha “APPROACH DEFINITIONS” lista detector(es) de extensão por aproximação e grupo: 1→12,13,14/SG9; 2→20,21,22/SG5; 3→23,24/SG6; 4→18,19/SG4; 5→16,17/SG3; 6→1/SG12; 7→2,3/SG13; 8→5,6/SG1; 9→7/SG7; 10→10,11/SG2. Os números 4 e 9 têm função de fila descrita nas notas, e 8 e 15 também constam nas funções/mapa, embora não apareçam como “extending detectors” nessa tabela.
- O diagrama “DETECTOR MAP” posiciona visualmente loops numerados em faixas e representa movimentos/ramais com os nomes Montague Street, West Gate Freeway e West Gate entry/exit ramps. As folhas “GROUP ALLOCATION” e “PHASING” dão os grupos e sequência/fases; as notas descrevem chamadas, extensões, filas e fechamentos de freeway.

Isso fecha parcialmente o caminho operação→aproximação dentro do desenho de 2014, mas **não valida a associação dado→desenho**: a definição de `NB_DETECTOR` no CSV é “SCATS Detector ID”; a planilha usa “DETECTOR No.” e “Internal / External Input Number”. Embora ambos os conjuntos no site 4901 contenham inteiros 1–24, nenhum campo ou nota DTP consultado declara que `NB_DETECTOR` equivale ao número de entrada do controlador. Igualdade numérica, isoladamente, não é crosswalk. Além disso, a folha de 2014 não informa data de efetividade, retirada ou verificação atual da instalação/configuração.

Para geometria, o artefato local versionado é [a rede OSM→SUMO de 27/10/2026](west-gate-sumo-network.md), cujo manifesto hashia o `.net.xml` como `006bd41d53d0a772150b1a672773f5ca2b857344c35c21cb91df2f984e0f79da`. Ele contém edges nomeadas `Montague Street`, `West Gate Freeway` e rampas Montague/West Gate. A folha 4901 é um diagrama de operação, sem coordenadas/CRS, levantamento ou identificador de edge/lane; seu desenho não estabelece uma transformação para IDs/faixas SUMO, e a rede SUMO é OSM-derivada, não as-built verificada. Assim, não atribuí nenhum `NB_DETECTOR` a edge/lane do SUMO.

**Stop reason para 4901:** mapping numérico folha↔CSV não declarado pelo DTP; folha de operação projetada em 2014 sem vigência confirmada para outubro/2026; diagrama não georreferenciado à rede SUMO. Há uma hipótese verificável a investigar com o DTP ou um crosswalk/configuração SCATS vigente, mas os materiais públicos consultados ainda não fecham a prova.

## CRS, resolução, período, licença e ambiguidades

- **CRS:** os campos são `LATITUDE`/`LONGITUDE`; a [metadata primária do recurso](https://opendata.transport.vic.gov.au/dataset/victorian-traffic-signals/resource/1036a318-8867-4dc6-bd84-fc3bcd6cbdb9) declara `Geographic Coordinate System: WGS84`. Essa declaração não foi verificada independentemente para os registros, e não foi atribuída uma codificação EPSG. As coordenadas foram usadas somente como filtro de busca por bbox, sem atribuir detector a via; a fonte não declara precisão, método de levantamento nem ponto de referência.
- **Volumes:** sem geometria/CRS; associação espacial depende do ID do site e de recurso espacial separado. `NB_DETECTOR` é um identificador local SCATS, sem direção/approach no CSV.
- **Resolução:** transições de estado a cada 15 min por detector, com 96 posições nomeadas por dia. A página declara `QT_INTERVAL_COUNT` em Australian Eastern Standard Time e descreve `V00` como 00:00–00:15. O material DTP consultado não define se, durante daylight saving em Victoria, esses bins permanecem em AEST fixo ou são convertidos para hora local; o alinhamento de outubro à hora civil/AEDT continua sem resolução oficial.
- **Período:** dataset geral de volumes desde 01/04/2014, frequência diária. Snapshot baixado de outubro de 2026: 01–26/10/2026 segundo metadados e atualização 27/10/2026. Folhas de configuração têm janela e atualização diferentes (ad hoc, até 16/06/2025), portanto vigência de cada layout face aos dados 2026 deve ser confirmada.
- **Licença:** CC BY 4.0 nos três recursos; manter atribuição ao Department of Transport and Planning, Victoria, ao redistribuir resultados/dados.
- **Limites de qualidade/cobertura:** nota do DTP diz máximo de 24 volume detectors por site, embora no CSV consultado dois sites do entorno tenham 32 IDs distintos (0–31). É necessário investigar se a nota está desatualizada, se IDs incluem categorias não comparáveis, ou se existe diferença de esquema/limitação antes de somar todos os detectores.
- **Sem inferências proibidas:** coordenada próxima a uma via, nome de rua, faixa, detector id em sequência ou volume do loop não bastam para decidir abordagem/direção/movimento. Também não implicam OD, entrada de rede ou rota.

## Caminho de associação e decisão de uso

O caminho de associação requerido continua sendo: `NB_SCATS_SITE` ↔ `SITE_NO` para localizar a folha; validar explicitamente `NB_DETECTOR` ↔ número do loop/controlador; confirmar que essa operação sheet estava vigente no período de observação; ligar a aproximação do mapa a uma edge/lane por fonte georreferenciada ou levantamento que corresponda à geometria versionada; validar funcionamento/configuração do loop e semântica de contagem; alinhar janelas horárias. No caso 4901, a folha de 2014 fornece detector→aproximação/grupo **dentro do desenho**, mas não resolve os demais elos.

**Gate contra circularidade/leakage:** é proibido usar a mesma linha SCATS para derivar ou ajustar a demanda e também calibrar a simulação ou reportar validação held-out. A identidade da linha para essa decisão futura é `(source, site, detector, interval, target_measure)`. Antes de qualquer avaliação empírica, pré-atribuir conjuntos disjuntos de chaves: `D` para derivação/ajuste de demanda, `C` para calibração e `H` para avaliação held-out, sem sobreposição (`D∩C = D∩H = C∩H = ∅`). Este relatório não atribui linhas reais a `D`, `C` ou `H`. Alternativamente, a validação deve usar uma fonte independente que não tenha participado da derivação/ajuste da demanda nem da calibração. Se essa separação prévia não for possível, não reportar calibração nem validação empírica com os mesmos registros.

**Conclusão binária: cannot currently be used.** Há medição SCATS em pontos espacialmente distintos do TIRTL, mas nenhum detector/site passou os gates para servir como restrição independente de demanda nesta rede. Para 4901, há mapa de loops e tabela de aproximações, porém sem crosswalk documentado para `NB_DETECTOR`, sem confirmação de vigência em 2026, sem correspondência validada a edge/lane SUMO e sem validação de comportamento de detecção. A declaração de AEST tampouco resolve o alinhamento durante daylight saving. Mesmo quando resolvidos, contagens pontuais mapeadas seriam fluxos locais observados, não demanda OD; qualquer avaliação deverá também passar o gate de separação prévia acima. Nenhum OD, rota ou resultado SUMO foi inferido ou criado aqui.

## Provenance / claim boundaries

| Claim | Evidência | Status | Permitido dizer | Limites |
|---|---|---|---|---|
| SCATS publica transições de estado de loops por site em 15 min | Página/dicionário DTP, fields `NB_SCATS_SITE`, `NB_DETECTOR`, `V00–V95` | `RESEARCH_SUPPORTED` | DTP publica transições detector/site em intervalos de 15 min | Não assumir contagens de veículos/fluxos verificados sem validar configuração e detecção; não é direção ou OD por padrão |
| Há cobertura perto dos acessos além dos TIRTL 504/505 | CSV oficial com campos lat/lon, metadata declara WGS84 + join ID exato ao CSV diário oficial em sites 2880/2881/2399/2886/2887/2896–2898/4901 | `RESEARCH_SUPPORTED` | Há medições SCATS em sinais nomeados dos acessos da área | Coordenadas usadas somente como filtro bbox; inventário e bbox não provam detector→via/movimento; locais de interseção são distintos dos sensores da ponte |
| A folha 4901 mapeia entradas do controlador a aproximações/grupos e desenha a posição dos loops | Workbook DTP `4750-4999/4901.htm`, abas Detector Functions, Approach Definitions, Detector Map, Group Allocation, Phasing; projeto datado de 30/04/2014 | `RESEARCH_SUPPORTED` para o conteúdo da folha | A operação sheet 4901 de 2014 lista detector→approach/group e representa loops/faixas | A identidade com `NB_DETECTOR`, a vigência em 2026 e edge/lane SUMO permanecem sem prova |
| Dados podem entrar como demanda independente agora | Mapping, horário e partição independente para demanda/calibração/holdout não demonstrados | `UNVERIFIED` / negado pela evidência atual | Nenhum uso como constraint até resolver a associação e o gate de separação | Não construir OD/rotas a partir destas contagens; nunca reutilizar as mesmas linhas para derivar/ajustar demanda e calibrar ou held-out validar |

**Artefatos:** este relatório documenta as URLs, o member ZIP e o hash do CSV diário usados para reprodução.
**Validação:** leitura Range oficial DTP, inspeção do dicionário, páginas e diagrama da folha 4901, cabeçalho/dados do dia 01/10/2026, filtros de bbox e joins de IDs reproduzidos localmente; sem alteração de código, calibração ou execução SUMO.
