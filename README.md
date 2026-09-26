# UrbanPulse NYC

Civic reporting for DivHacks **Hack the City**: hazard photo → Grok ticket → Tiger Data.

## Quick start

```powershell
cd C:\Users\burni\Projects\urbanpulse-nyc
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env: set XAI_API_KEY (and DATABASE_URL for Tiger Data)
.\run.ps1
```

Open http://localhost:8501

## What to configure

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `XAI_API_KEY` | For live Grok | xAI API key |
| `GROK_MODEL` | No (default `grok-4.6`) | Vision-capable chat model |
| `DATABASE_URL` | No | Tiger Data Postgres URL; else local `urbanpulse.db` |

## App tabs

1. **Report** — area/streets → photo → Grok (or mock) → save ticket  
2. **Planner dashboard** — recent rows, severity-by-hour chart, map pins  

## Layout

```
src/
  app.py            # Streamlit UI
  grok_client.py    # xAI / mock vision
  models.py         # Pydantic DispatchTicket
  nearby_places.py  # 1-mile street suggestions
  db.py             # SQLAlchemy + Timescale helpers
```
