# 🚕 FareCompass - Compare cab fares across Mumbai

FareCompass is a Streamlit web app that lets riders tap a map to set their route, then compares estimated fares for
auto, taxi, sedan and SUV across Ola, Uber, Rapido and the Kaali-Peeli meter - with live weather, advance booking and
suggestions for food, shopping and sights along the way.

> **Before a public launch:** fares are *estimates* produced by transparent pricing rules in `platform_fares.json`
> (editable) and a fare estimator trained on **simulated** trips. The platform prices are not live or official, and the
> estimator has not been validated against real receipts. The app says "estimates only / not affiliated with Ola, Uber or
> Rapido" in its footer - keep that, validate with real fares, and run a trademark/domain check on the brand name
> (set in `branding.py`) before launching.

## What users can do
- **Tap the map** (opens straight away) to set pickup, optional stops and drop-off - or search for a place by name.
- **Compare ride options** for Auto / Taxi / Sedan / SUV; the lowest fare is highlighted and unavailable options say so.
- **Leave now or schedule** a trip up to 7 days ahead; weather, traffic and rush-hour/night pricing follow that time.
- **See conditions:** automatic weather (temperature, rain, wind, humidity, next-hours outlook), traffic estimate, arrival time.
- **Discover places on the way:** restaurants, cafés, malls and attractions near the route, timed to the trip, with one-click "＋ Stop".
- **Save trips** and download them from *My trips*.
- **Performance tab:** R² score, average error, actual-vs-predicted graph and feature importance for the fare estimator (measured on simulated trips, grouped by unseen route areas).

## Project structure
```
app.py                    Streamlit interface
branding.py               Name, tagline and brand colours (change here to rebrand)
ui_components.py          HTML/CSS building blocks (all external text is escaped)
.streamlit/config.toml    Light theme + navy primary colour
fare_logic.py             Pricing rules, traffic estimate, fare estimator wrapper (shared with training)
platform_fares.json       Editable platform rates, surge, rain and vehicle multipliers
route_engine.py           OSRM routing + clearly flagged fallback
geo_utils.py              Rate-limited, Mumbai-bounded place search (Nominatim)
weather_service.py        Open-Meteo weather -> pricing flag + display data
trip_time.py              Current India time + advance-booking validation
poi_service.py            Places along the route (Overpass / OpenStreetMap) + ranking
database.py               SQLite trip log (parameterised, auto-migrating, per-session)
train_mumbai_model.py     Rebuilds the simulated dataset and the fare estimator (optional)
tests/                    Unit tests
```

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py
python -m unittest discover -s tests -v      # tests
python train_mumbai_model.py                 # optional: rebuild the fare estimator
```
Optional environment variables: `MAP_TILE_URL`, `MAP_TILE_ATTR`, `OSRM_BASE_URL`, `FARE_DB_PATH`, `NOMINATIM_USER_AGENT`.

## Services used (all free, no API keys)
| Purpose | Service | Notes |
|---|---|---|
| Map tiles | OpenStreetMap standard tiles | no key needed; light use only - for production set `MAP_TILE_URL` / `MAP_TILE_ATTR` to a licensed provider (MapTiler, Stadia, Mapbox) or self-host |
| Routing | OSRM demo server | light use only - self-host OSRM for production |
| Place search | Nominatim | max 1 request/second (handled) |
| Weather | Open-Meteo | non-commercial use; hourly forecast up to a week ahead |
| Places on the way | Overpass API | public servers can be busy; app falls back to a mirror |

## Known limitations
- Place suggestions come from OpenStreetMap, which has no ratings or crowd data; hours may be missing or outdated.
- Weather is read at the pickup point for the trip hour (not along the whole route).
- Verify the Kaali-Peeli tariff and the night-surcharge window (`fare_logic.NIGHT_START_HOUR/NIGHT_END_HOUR`).
- Vehicle multipliers in `platform_fares.json` are assumptions.
- "Save this trip" logs a comparison; it does not book a cab.
- Saved trips are stored per browser session in a local SQLite file; add accounts before multi-user production use.

## License
MIT - see `LICENSE`.
