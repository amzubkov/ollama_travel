# Travel Deals Agent

Local MVP for finding unusually cheap flights and promo bundles, with analysis by GLM 5.2 in Ollama Cloud.

## Setup

```bash
cd ~/Dev/travel-deals-agent
cp .env.example .env
cp config/sources.example.json config/sources.json
uv sync
```

Set `OLLAMA_API_KEY` in `.env`.

## Run

```bash
uv run travel-deals scan
```

Dry run without LLM:

```bash
uv run travel-deals scan --no-llm
```

Show stored deals:

```bash
uv run travel-deals list
```

## Docker

Build and run one scan:

```bash
docker compose build
docker compose run --rm agent scan
```

Run status:

```bash
docker compose run --rm agent status
```

The first version collects RSS deals, stores them in SQLite, scores them, and asks GLM 5.2 to extract conditions, risks, and a short alert summary.
