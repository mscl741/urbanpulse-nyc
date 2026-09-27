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

## Photon iMessage

Spectrum listens for iMessage and forwards hazard questions, text reports, and photos to the existing Python app. Nothing in this path is a second hazard database.

**Public texting number:** **(628) 789-5365** — residents can iMessage this number from an iPhone. The home page of the live app also shows this number and how-to steps.

Quick checks:

| You send | What happens |
|----------|----------------|
| `Hello` | Reply: `Hello from UrbanPulse.` |
| `What hazards are near Harlem?` | Near-me scan for that neighborhood |
| `Report a large pothole at Broadway and W 116th St.` | Text report filed onto the live map |
| Photo + caption `This is at Broadway and W 116th St.` | Vision classify + pin on the live map |

From the repo root, in three terminals:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# set XAI_API_KEY in .env
python src\imessage_bridge.py
```

```powershell
cd spectrum
copy .env.example .env
# set SPECTRUM_PROJECT_ID and SPECTRUM_PROJECT_SECRET
npm install
npm start
```

```powershell
.\run.ps1
```

On macOS or Linux, use `python -m venv .venv`, `source .venv/bin/activate`, `cp .env.example .env`, and `streamlit run src/app.py` instead of the PowerShell helpers. Run `npm start` from `spectrum/` so it loads `spectrum/.env`. Node 20 or newer is required. In the Photon project settings, connect iMessage, then text **Hello**. The reply is `Hello from UrbanPulse.` Other messages need the bridge running on port 8766.

## What to configure

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `XAI_API_KEY` | For live Grok | xAI API key. Without it, iMessage reports are saved as mock |
| `GROK_MODEL` | No (default `grok-4.6`) | Vision-capable chat model |
| `DATABASE_URL` | No | Tiger Data Postgres URL; else local `urbanpulse.db` |
| `SPECTRUM_PROJECT_ID` | For iMessage | Photon project id, in `spectrum/.env` |
| `SPECTRUM_PROJECT_SECRET` | For iMessage | Photon project secret, in `spectrum/.env` |
| `URBANPULSE_BRIDGE_URL` | No | Spectrum → bridge URL. Default `http://127.0.0.1:8766` |
| `PHOTON_IMESSAGE_NUMBER` | No | Public text number shown on Home. Default `628-789-5365` |

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
