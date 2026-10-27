# Avaliação delimitada: SCATS no West Gate

**Data da consulta:** 2026-10-27  
**Escopo:** somente Open Data Victoria/DTP; nenhuma rota, OD ou simulação SUMO foi criada/executada.  
**Decisão binária:** **SCATS cannot currently be used as independent demand constraints for this network.**

## Resultado

Há cobertura espacial SCATS relevante além dos TIRTL 504/505. O DTP publica contagens de loops de tráfego SCATS por site/detector, em bins de 15 minutos, separadamente dos dados TIRTL; e publica um inventário georreferenciado dos sinais. O join reproduzível para localizar sinais é por `SITE_NO` do inventário versus `NB_SCATS_SITE` dos volumes, não por nearest point.

Esse join chega ao **site**, mas os volumes não trazem aproximação, faixa, movimento, rumo ou grupo de sinal. O DTP publica operation sheets que declaram documentar funções de detectores/grupos e fases, porém nesta auditoria não foi verificado o conteúdo de uma folha específica contra os identificadores `NB_DETECTOR` observados. Portanto ainda não existe associação demonstrada detector→movimento/rede para as contagens candidatas. Contagens de entrada/saída no próprio detector também não definem OD nem rotas.

## Evidência e reprodução

### Fontes oficiais

1. **[Traffic Signal Volume Data (SCATS)](https://opendata.transport.vic.gov.au/dataset/traffic-signal-volume-data)** — DTP declara contagens por loop/detector e site, agregadas em períodos de 15 minutos, fonte SCATS, atualização diária e reporte desde 1 de abril de 2014. A licença é CC BY 4.0. A página alerta para limite/cobertura máxima de 24 volume detectors por site.
2. **[Victorian Traffic Signals](https://opendata.transport.vic.gov.au/dataset/victorian-traffic-signals)** — inventário DTP de sinais em operação, CSV, CC BY 4.0. O recurso declara os campos `SITE_NO` (identificador do site de sinal), `SITE_NAME`, `TYPE`, `MUNICIPALITY`, `LATITUDE`, `LONGITUDE`; CRS geográfico WGS84; cobertura Victoria.
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

## CRS, resolução, período, licença e ambiguidades

- **CRS:** inventário declara Geographic Coordinate System WGS84 para latitude/longitude. Trate os valores como coordenadas geográficas WGS84 (EPSG:4326) para consulta espacial; a fonte não declara precisão, método de levantamento nem ponto de referência (centro do cruzamento, gabinete, etc.). A caixa acima é só um recorte de busca e não prova interseção detector-rede.
- **Volumes:** sem geometria/CRS; associação espacial depende do ID do site e de recurso espacial separado. `NB_DETECTOR` é um identificador local SCATS, sem direção/approach no CSV.
- **Resolução:** contagens de transição a cada 15 min por detector, com 96 posições nomeadas por dia. A página declara timestamp em AEST. Como o período de outubro está durante horário de verão de Victoria, não usar os horários como relógio local/AEDT sem resolver a convenção do export; permanece ambíguo se os bins são mantidos em AEST fixo ou convertidos para hora local.
- **Período:** dataset geral de volumes desde 01/04/2014, frequência diária. Snapshot baixado de outubro de 2026: 01–26/10/2026 segundo metadados e atualização 27/10/2026. Folhas de configuração têm janela e atualização diferentes (ad hoc, até 16/06/2025), portanto vigência de cada layout face aos dados 2026 deve ser confirmada.
- **Licença:** CC BY 4.0 nos três recursos; manter atribuição ao Department of Transport and Planning, Victoria, ao redistribuir resultados/dados.
- **Limites de qualidade/cobertura:** nota do DTP diz máximo de 24 volume detectors por site, embora no CSV consultado dois sites do entorno tenham 32 IDs distintos (0–31). É necessário investigar se a nota está desatualizada, se IDs incluem categorias não comparáveis, ou se existe diferença de esquema/limitação antes de somar todos os detectores.
- **Sem inferências proibidas:** coordenada próxima a uma via, nome de rua, faixa, detector id em sequência ou volume do loop não bastam para decidir abordagem/direção/movimento. Também não implicam OD, entrada de rede ou rota.

## Caminho de associação e decisão de uso

O caminho oficial disponível é: `NB_SCATS_SITE` ↔ `SITE_NO` para alcançar o site/folha; na folha vigente, ler `Detectors`, `Signal Groups`, `Operation Notes` e `Phasing` para atribuir cada laço a uma abordagem/sentido/faixa; verificar a semântica dos IDs contra as colunas do arquivo de volume; então ligar a abordagem à geometria viária/versionada e alinhar janelas horárias. A publicação dos operation sheets torna esse procedimento verificável em princípio, mas esta consulta não validou uma folha concreta de site contra `NB_DETECTOR` nem estabeleceu vigência para outubro/2026. A etapa crítica detector→movimento continua aberta.

**Conclusão binária: cannot currently be used.** Os volumes são uma fonte de medição independente do TIRTL e há cobertura espacial relevante fora dos sites 504/505, mas ainda não servem como restrições empíricas de demanda para esta rede sem o mapping individual dos detectores, confirmação de vigência, resolução de horário e regra de interpretação/agregação. Depois desses gates, loops mapeados podem ser constraints observadas de fluxos locais para calibração/validação; não são por si só demanda OD independente. Nenhum OD, rota ou resultado SUMO foi inferido ou criado aqui.

## Provenance / claim boundaries

| Claim | Evidência | Status | Permitido dizer | Limites |
|---|---|---|---|---|
| SCATS publica transições de estado de loops por site em 15 min | Página/dicionário DTP, fields `NB_SCATS_SITE`, `NB_DETECTOR`, `V00–V95` | `RESEARCH_SUPPORTED` | DTP publica transições detector/site em intervalos de 15 min | Não assumir contagens de veículos/fluxos verificados sem validar configuração e detecção; não é direção ou OD por padrão |
| Há cobertura perto dos acessos além dos TIRTL 504/505 | CSV oficial WGS84 + join ID exato ao CSV diário oficial em sites 2880/2881/2399/2886/2887/2896–2898/4901 | `RESEARCH_SUPPORTED` | Há medições SCATS em sinais nomeados dos acessos da área | Inventário e bbox não provam detector→via/movimento; locais de interseção são distintos dos sensores da ponte |
| Operação sheets oferecem uma rota para detector→movimento | Descrição oficial e campos `Detectors`, `Signal Groups`, `Operation Notes`, `Phasing` | `RESEARCH_SUPPORTED` (capacidade declarada) | DTP publica material por site que descreve operação de detector/sinal | Não foi validado um sheet individual versus `NB_DETECTOR`/data de vigência |
| Dados podem entrar como demanda independente agora | Mapping e horário não demonstrados | `UNVERIFIED` / negado pela evidência atual | Nenhum uso como constraint até resolver a associação | Não construir OD/rotas a partir destas contagens |

**Artefatos:** este relatório apenas; os downloads temporários foram removidos.  
**Validação:** download oficial, inspeção do dicionário/cabeçalho, filtros de bbox, join de IDs e contagens diárias reproduzidos localmente; sem testes de código e sem execução SUMO.
