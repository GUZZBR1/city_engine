# Urban Twin Arena — Arena de Tráfego

Projeto experimental para explorar e comparar cenários de tráfego numa cidade sintética. O MVP atual apresenta a rede de Aurora, executa simulações com [SUMO](https://sumo.dlr.de/) e permite comparar um plano semafórico base com uma intervenção, mantendo as mesmas condições de entrada.

> **Limite científico:** Aurora, sua rede, demanda e temporizações são sintéticas. Os resultados demonstram o funcionamento do software; não são medições nem previsões validadas para uma cidade real.

## O que funciona hoje

- Geração determinística do snapshot `aurora-base-v1` a partir de YAML.
- Interface web para explorar distritos, vias e cruzamentos.
- Simulação de tráfego via SUMO, com métricas de viagens, tempos, velocidade e filas.
- Comparação pareada entre a configuração base e uma intervenção semafórica declarativa. A demonstração altera as fases do nó `node:02:00` para `[40, 3, 20, 3]` segundos, preservando o ciclo de 66 segundos.
- API FastAPI com execução de simulações e comparações em segundo plano.

A comparação mantém iguais snapshot, rede, demanda, janela, semente e limite de escoamento. Os resultados incluem métricas, diferenças entre os cenários, unidades e avisos por cenário.

## Tecnologias

- Python 3.11+, FastAPI e Pydantic
- SUMO (`sumo` e `netconvert`)
- React, TypeScript, Vite e MapLibre

## Executar localmente

### API e SUMO

Requer Python 3.11+ e `uv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install uv
uv pip install --python .venv/bin/python \
  -e ./packages/urban_arena \
  -e ./packages/simulation \
  -e ./apps/api \
  eclipse-sumo
sumo --version
netconvert --version
uvicorn app.main:app --app-dir apps/api --reload
```

A API fica em `http://127.0.0.1:8000`; a documentação OpenAPI está em `http://127.0.0.1:8000/docs`.

### Interface web

Em outro terminal, com Node.js 20+:

```bash
cd apps/web
npm ci
cp .env.example .env.local
npm run dev
```

Abra o endereço informado pelo Vite, geralmente `http://localhost:5173`.

## Verificações

```bash
# Na raiz do projeto, com .venv ativado
uv pip install --python .venv/bin/python pytest
python -m pytest packages/urban_arena/tests packages/simulation/tests apps/api/tests

# Em apps/web
npm test
npm run build
```

## Estrutura

```text
configs/cities/       Configuração versionada da cidade sintética
packages/urban_arena/ Geração do snapshot e contratos da cidade
packages/simulation/  Contratos do motor, compilação e adaptador SUMO
apps/api/             API e execução dos jobs
apps/web/             Interface de mapa e comparação de cenários
docs/                 Conceito, arquitetura e plano do piloto empírico
```

## Limitações atuais

- Os jobs ficam em memória e são perdidos quando a API reinicia; ainda não há fila persistente nem cancelamento.
- A comparação disponível é demonstrativa e usa uma semente. Ela não sustenta conclusões estatísticas sobre a intervenção.
- Os planos semafóricos e parâmetros de tráfego são hipóteses sintéticas, não foram calibrados com observações reais.
- As cinco empresas/agentes da Arena e a comparação de suas políticas ainda não estão implementadas.

Consulte [`docs/conceito/urban-twin-arena.md`](docs/conceito/urban-twin-arena.md), [`docs/arquitetura/cidade-sintetica-urban-twin-arena.md`](docs/arquitetura/cidade-sintetica-urban-twin-arena.md) e [`docs/piloto/ficha-piloto.md`](docs/piloto/ficha-piloto.md) para o escopo e as próximas etapas.
