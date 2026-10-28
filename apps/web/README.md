# Frontend MVP 0 — Urban Twin Arena: Arena de Tráfego

Interface React + TypeScript para a Arena de Tráfego: consulta os metadados e a geometria da rede viária sintética Aurora, exibe seu esquema 2D e executa uma competição pareada entre cinco políticas de operação semafórica. Esta primeira rodada altera o controlador de um cruzamento; obras, pavimentação e rodovias ainda não estão modeladas.

## Executar localmente

Requisitos: Node.js 20+ e a API FastAPI do projeto disponível em `http://127.0.0.1:8000`.

```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

Abra a URL informada pelo Vite (por padrão `http://localhost:5173`). Para outra URL de API, defina `VITE_API_BASE_URL` em `.env.local`; o frontend acrescenta os caminhos `/api/v1/...`.

Endpoints consumidos:

- `GET /api/v1/cities/aurora-base-v1`
- `GET /api/v1/cities/aurora-base-v1/map`
- `POST /api/v1/simulations`
- `GET /api/v1/simulations/{simulation_id}`
- `POST /api/v1/comparisons`
- `GET /api/v1/comparisons/{comparison_id}`
- `POST /api/v1/traffic-competitions`
- `GET /api/v1/traffic-competitions/{competition_id}`

Os resultados e métricas vêm da API. A interface solicita um escoamento de até
3.600 s após a janela de demanda: nenhuma partida nova ocorre nesse período, e
veículos que não terminarem até o limite aparecem como não concluídos. O
comprimento médio de fila cobre somente a janela de demanda; médias nulas
aparecem como indisponíveis. O painel de competição executa uma base e cinco
políticas fixas para `node:02:04`, com a mesma rede, demanda, janela, semente,
limite de escoamento e ciclo semafórico. Exibe os resultados e deltas de cada
empresa, além do snapshot e identidade da referência. Se uma execução falhar,
a API não publica resultados parciais. Esta competição é um benchmark sintético
de operação semafórica, sem validação empírica; não modela ainda orçamento,
obras, manutenção ou infraestrutura de rodovias. A API local mantém jobs em
memória e não oferece cancelamento nesta etapa.

## Coordenadas e proveniência

A API fornece geometria no espaço cartesiano métrico `synthetic_local_cartesian_m`. A interface faz uma transformação afim em memória apenas para desenhar a grade no MapLibre. Não há mapa-base, persistência ou exportação das coordenadas de exibição; Aurora é identificada como esquema sintético local, sem localização geográfica real.

Se uma requisição falhar ou os metadados e o mapa divergirem em identidade/hash, o mapa e os dados são descartados até nova tentativa.

## Verificações

```bash
npm test
npm run build
```
