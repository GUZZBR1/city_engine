# Frontend MVP 0 — Urban Twin Arena: Arena de Tráfego

Interface React + TypeScript para a bancada de tráfego: consulta os metadados e a geometria da rede viária sintética Aurora e exibe seu esquema 2D sem mapa-base. Esta etapa visualiza a rede e compara cenários pareados; as cinco empresas competidoras são o próximo estágio do produto, ainda não executado pela aplicação.

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

Os resultados e métricas vêm da API. A interface solicita um escoamento de até
3.600 s após a janela de demanda: nenhuma partida nova ocorre nesse período, e
veículos que não terminarem até o limite aparecem como não concluídos. O
comprimento médio de fila cobre somente a janela de demanda; médias nulas
aparecem como indisponíveis. A API local mantém jobs em memória e não oferece
cancelamento nesta etapa. O painel também permite executar uma comparação
pareada entre a base e a temporização declarada para `node:02:04`, alcançada
por rotas da demanda do pico da manhã. Ele exibe
base, intervenção e deltas com unidades, além do snapshot, janela, semente,
escoamento, identidade das execuções e avisos por cenário. A intervenção
demonstrativa usa `[40, 3, 20, 3]` s, preservando o ciclo base de 66 s; é um
benchmark sintético sem validação empírica. A interface mostra o estado de
exposição: confirmada por rota válida que atravessa o nó, nenhuma rota válida
atravessa o nó, ou não verificável porque o arquivo de rotas está ausente,
inválido ou incompleto. Deltas iguais a zero são exibidos fielmente e não são
tratados como sucesso nem fracasso do cenário.

## Coordenadas e proveniência

A API fornece geometria no espaço cartesiano métrico `synthetic_local_cartesian_m`. A interface faz uma transformação afim em memória apenas para desenhar a grade no MapLibre. Não há mapa-base, persistência ou exportação das coordenadas de exibição; Aurora é identificada como esquema sintético local, sem localização geográfica real.

Se uma requisição falhar ou os metadados e o mapa divergirem em identidade/hash, o mapa e os dados são descartados até nova tentativa.

## Verificações

```bash
npm test
npm run build
```
