# Prompts para dividir o MVP 0 em três chats

Use este arquivo como instrução comum. Cada chat deve ler também:

- [Arquitetura completa](../arquitetura/arquitetura-completa-urban-twin-arena.md)
- [Blueprint de Aurora](../arquitetura/cidade-sintetica-urban-twin-arena.md)
- [Configuração padrão `aurora-base-v1`](../../configs/cities/aurora-base-v1.yaml)

Este roteiro foi escrito antes da implementação do MVP 0. O núcleo, a API e a interface agora existem; use os prompts abaixo como registro dos contratos e critérios originais, não como indicação de trabalho ainda pendente. Todo trabalho deve ficar dentro da raiz do projeto. Os chats têm ownership de arquivos diferente; não sobrescreva mudanças alheias. Se uma interface compartilhada precisar mudar, descreva a proposta e comunique ao chat integrador.

## Uso de agentes em cada chat

Cada chat deve pedir ajuda a **dois subagentes nativos** em tarefas independentes e limitadas: um revisa o desenho e outro verifica critérios/contratos. O chat principal continua responsável pelos arquivos, integração e decisão final. Os subagentes fazem revisão de leitura e não editam os arquivos do chat principal.

Use a ferramenta nativa de subagentes com `agent_type` explícito. Não simule esses papéis escrevendo apenas “aja como arquiteto/revisor”. Se a superfície de chat não oferecer roteamento nativo por `agent_type`, execute sem subagente e registre essa limitação.

| Chat | Revisor de desenho | Revisor de verificação |
|---|---|---|
| 1 — Núcleo da cidade | `architect`: schema e geração da rede | `verifier`: determinismo, balanços e critérios |
| 2 — API | `architect`: fronteiras e contrato HTTP | `verifier`: schemas, erros e comportamento |
| 3 — Frontend | `designer`: interação, acessibilidade e mapa | `verifier`: integração API, estados e proveniência |

Cada subagente retorna achados ao chat principal; o chat principal integra as mudanças sem delegar ownership dos arquivos.

## Ordem recomendada

1. **Chat 1 — Núcleo da cidade:** definir e implementar o contrato Python e o gerador determinístico.
2. **Chat 2 — API:** expor os contratos do Chat 1 pelos endpoints fixados neste arquivo.
3. **Chat 3 — Frontend:** construir a visualização consumindo o contrato HTTP fixado aqui.

O Chat 3 pode começar o shell visual em paralelo, mas deve usar o contrato abaixo; não deve criar uma segunda implementação do estado da cidade. A integração final e a resolução de conflitos ficam com o chat principal.

---

## Chat 1 — Schema e gerador determinístico de Aurora

```text
Implemente o núcleo do MVP 0 da Urban Twin Arena: carregar e validar a cidade sintética `aurora-base-v1`, gerar seu snapshot e criar cópias iniciais idênticas para os agentes.

Leia primeiro `docs/execucao/prompts-mvp0-3-chats.md`, `docs/arquitetura/arquitetura-completa-urban-twin-arena.md`, `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` e `configs/cities/aurora-base-v1.yaml`.

Ownership exclusivo deste chat:
- `packages/urban_arena/`
- `packages/urban_arena/pyproject.toml`, se necessário para empacotar o módulo
- Não edite `apps/api/`, `apps/web/` nem altere os valores de `configs/cities/aurora-base-v1.yaml`.

Entregue:
1. Schema tipado para validar a configuração YAML e mensagens de erro úteis.
2. Gerador puro/determinístico de snapshot para os distritos e a rede 5x5 de Aurora, incluindo as duas travessias da barreira especificadas no YAML.
3. Representação geográfica serializável como `LocalFeatureCollection`, em metros locais, para distritos, vias e cruzamentos. Não rotule coordenadas locais como GeoJSON RFC 7946.
4. Hash canônico do snapshot, independente de ordem incidental de serialização.
5. Função para criar cinco cópias independentes com o mesmo estado inicial e hash; mutação numa cópia não pode alterar as outras.
6. Um contrato de saída estável para consumo pela API, conforme este arquivo.

Restrições:
- `aurora-base-v1.yaml` é a fonte dos parâmetros; não duplique os números em código.
- Mantenha população, empregos, orçamento e modal share consistentes com a configuração.
- Mantenha proveniência `synthetic` nos dados gerados.
- Não implemente FastAPI, interface web, SUMO ou agentes treináveis nesta tarefa.
- Se os detalhes geométricos ainda insuficientes impedirem uma escolha, use a menor regra determinística compatível com o blueprint e documente-a; não altere silenciosamente a configuração-base.

Critérios de conclusão:
- A mesma configuração e versão geram o mesmo hash.
- Totais do snapshot correspondem aos totais da configuração.
- Há 5 cópias independentes com hash inicial idêntico.
- Cada feature local tem ID estável, propriedades tipadas e coordenadas em metros.
- Informe arquivos alterados, decisões geométricas e validações executadas.

Antes de codificar, delegue uma revisão do desenho a um subagente nativo `architect` e a verificação dos critérios a um subagente nativo `verifier`, ambos em leitura apenas. Integre você mesmo os achados.
```

## Contrato comum de dados/API

O núcleo deve produzir um objeto equivalente a:

```json
{
  "city_id": "aurora-base-v1",
  "snapshot_id": "aurora-base-v1:<hash>",
  "name": "Aurora",
  "schema_version": "1",
  "provenance": "synthetic",
  "hash": "<sha256>",
  "population": {
    "total": 67250,
    "urban": 58783,
    "rural_catchment": 8467
  },
  "jobs": 24000,
  "coordinate_space": "synthetic_local_cartesian_m",
  "bounds_m": [0, 0, 6000, 6000],
  "layers": {
    "districts": {"type": "LocalFeatureCollection", "features": []},
    "edges": {"type": "LocalFeatureCollection", "features": []},
    "nodes": {"type": "LocalFeatureCollection", "features": []}
  }
}
```

`LocalFeatureCollection` é um contrato próprio em coordenadas cartesianas locais, não GeoJSON RFC 7946 nem latitude/longitude. O frontend transforma as coordenadas apenas para exibição no MapLibre, usa estilo sem mapa-base e identifica a tela como esquema sintético local. Não persiste nem exporta coordenadas de exibição como geografia real. Os números de população e emprego devem ser lidos da configuração, não hard-coded.

---

## Chat 2 — API FastAPI para cidade e mapa

```text
Implemente a API HTTP do MVP 0 da Urban Twin Arena para consultar Aurora e a geometria local gerada pelo núcleo Python.

Leia primeiro `docs/execucao/prompts-mvp0-3-chats.md` e a arquitetura completa. Use o contrato de dados/API deste arquivo. Integre com `packages/urban_arena/`; não reimplemente o gerador.

Ownership exclusivo deste chat:
- `apps/api/`
- `apps/api/pyproject.toml` ou dependências locais equivalentes, se necessário
- Não edite `packages/urban_arena/`, `apps/web/` nem a configuração de Aurora.

Endpoints do MVP:
- `GET /api/v1/health` → status simples da API.
- `GET /api/v1/cities/aurora-base-v1` → metadados do snapshot, hash, população, empregos e proveniência.
- `GET /api/v1/cities/aurora-base-v1/map` → bounds e FeatureCollections de distritos, vias e cruzamentos.

Requisitos:
- FastAPI + Pydantic; schemas de resposta explícitos.
- Respostas e OpenAPI compatíveis com o contrato congelado acima.
- Erros claros para cidade não encontrada e falha ao gerar/carregar snapshot.
- API não executa SUMO nem simulação dentro do request.
- Sem banco de dados no MVP 0, salvo se a integração exigir; documente antes de adicionar.
- CORS restrito à origem local de desenvolvimento; configuração via ambiente.
- As camadas usam `LocalFeatureCollection` em metros locais, não GeoJSON geográfico.

Critérios de conclusão:
- Os três endpoints respondem e o OpenAPI descreve os schemas.
- Os metadados e a geometria vêm do pacote `urban_arena`, sem números duplicados na API.
- Informe como executar a API, arquivos alterados e validações executadas.

Antes de codificar, delegue a revisão do contrato a um subagente nativo `architect` e a verificação de schemas/erros a um subagente nativo `verifier`, ambos em leitura apenas. Integre você mesmo os achados.
```

---

## Chat 3 — Interface React/TypeScript + MapLibre

```text
Implemente o frontend do MVP 0 da Urban Twin Arena: exibir Aurora no mapa 2D a partir da API, com legenda e indicação explícita de dados sintéticos.

Leia primeiro `docs/execucao/prompts-mvp0-3-chats.md` e a arquitetura completa. Consuma exatamente o contrato HTTP abaixo; não gere uma cidade alternativa nem calcule métricas científicas no navegador.

Ownership exclusivo deste chat:
- `apps/web/`
- `apps/web/package.json` e arquivos de build locais, se necessários
- Não edite `packages/urban_arena/`, `apps/api/` nem `configs/cities/aurora-base-v1.yaml`.

Endpoints esperados:
- `GET /api/v1/cities/aurora-base-v1`
- `GET /api/v1/cities/aurora-base-v1/map`
- Base URL configurável por variável de ambiente, com padrão local documentado.

Tela inicial:
- Mapa central com limites da cidade, distritos, vias e cruzamentos.
- Painel lateral com nome, hash do snapshot, população, empregos e classificação `SINTÉTICO`.
- Legenda persistente e controles para ligar/desligar camadas.
- Estados de carregamento, erro de API e botão de nova tentativa.
- Resumo tabular acessível equivalente aos elementos essenciais do mapa.

Requisitos:
- React + TypeScript + MapLibre GL JS.
- Transformar coordenadas métricas locais para o espaço de exibição do MapLibre sem persistir as coordenadas convertidas como dado do domínio.
- Usar estilo sem mapa-base e identificar a tela como esquema sintético local; Aurora não deve parecer estar numa localização real.
- Cores não podem ser o único meio de distinguir camadas ou proveniência.
- Sem cálculos de população, score, orçamento ou transições no cliente.
- Não conectar SUMO, agentes ou autenticação nesta etapa.

Critérios de conclusão:
- Tela abre e renderiza dados recebidos da API.
- Legenda identifica Aurora como cidade sintética.
- Falha de API não deixa mapa enganoso ou dados antigos rotulados como atuais.
- Informe comandos de execução, arquivos alterados e validações executadas.

Antes de codificar, delegue uma revisão de interação/acessibilidade a um subagente nativo `designer` e a verificação da integração/estados a um subagente nativo `verifier`, ambos em leitura apenas. Integre você mesmo os achados.
```

## Integração final neste chat

Depois dos três slices, integrar sem mover ownership antes de revisar os contratos. Critérios do MVP 0:

- YAML → snapshot determinístico → cinco cópias iniciais idênticas.
- API expõe metadados e geometria local gerados pelo mesmo snapshot.
- Frontend mostra a mesma versão/hash que a API.
- Coordenadas aparecem como grade sintética local projetada para exibição, não como mapa real.
- Documentação de execução local explica como iniciar núcleo, API e web.

SUMO, banco, jobs de simulação e treinamento de agentes ficam para o MVP seguinte.
