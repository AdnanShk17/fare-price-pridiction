# Changes in this version

## Bugs fixed
- Crash after "Clear Stops"/"Clear Trip" (`stops.index(None)` on an empty list; `adding_stop` never reset).
- Search box silently overwrote map clicks on every rerun; geocoding now runs only on a button press, is cached,
  rate-limited, region-bounded (no more Pune results) and has timeouts + error handling.
- Same map click being re-applied on every rerun (pickup+drop filled by one click) - clicks are de-duplicated.
- Bookings saved with empty pickup/drop in Hub/Custom modes; "Selected Locations" panel was blank there too.
- Leftover map stops leaked into hub/custom routes.
- Fare shown for hard-coded default coordinates before any map selection.
- Save button / bar chart placed outside the tab; now inside the comparison section.
- Report tab hidden when metrics file missing; stray subheader in the wrong branch.
- Result map ignored the selected tile provider.
- Failed OSRM calls were silently replaced by straight-line values (now flagged) and are never cached.
- Training script blocked on `plt.show()` and used cwd-relative output paths.

## ML / data
- One shared pricing module (`fare_logic.py`) for training and the app: no train/serve skew, no double-applied
  weather/peak/night multipliers, consistent Kaali-Peeli rules, per-platform surge from the JSON.
- Training distances are now road-like (detour factor) and durations use the app's traffic multiplier.
- Removed features that carry no signal (lat/lon, passengers, weekday).
- Model predicts fare/baseline ratio → sensible extrapolation beyond 160 km; 129 MB → ~4.5 MB (under GitHub's limit).
- Grouped (unseen-area) evaluation + grouped CV + linear baseline; honest `data_source: simulated` in metrics.

## Honesty / docs
- README/app/viva text now says the data is simulated, OSRM gives the *fastest* route with no live traffic, traffic is
  a heuristic, corrected complexity claims, and numbers in the report tab are read from the metrics file.

## Engineering
- OSRM over HTTPS, `OSRM_BASE_URL` override, coordinate validation, caching of successful routes.
- SQLite: context-managed connections, auto-migration, per-session bookings, input length limits, CSV export.
- Removed unused NYC CSVs and unused imports; added `requirements.txt`, `.gitattributes` (LF), tests, EDA with findings.

## Update: platform prices now follow the vehicle category
- Previously only "Our Model" changed when you switched the vehicle; Ola/Uber/Rapido/Kaali-Peeli stayed fixed.
- Each platform now has `vehicle_multipliers` in `platform_fares.json`. Switching Auto / Taxi / Sedan / SUV updates every card.
- A platform that does not offer a category (e.g. Kaali-Peeli SUV) shows **N/A** and is left out of the cheapest-pick and the chart.
- Saved bookings store NULL for unavailable platforms.

## Update: automatic weather, automatic time / advance booking, route suggestions
- **Weather API:** `weather_service.py` reads the hourly Open-Meteo forecast for the pickup point and trip hour and sets the
  fare model's weather flag automatically (rain intensity + WMO code). Manual mode remains, and is used automatically if the
  API is unreachable.
- **Time:** trip time defaults to the current India time (IST, no tzdata needed). "Schedule for later" adds a date and time
  picker (up to 7 days ahead, past times rejected). Peak/night pricing, weather and suggestions all use the chosen time.
- **Suggestions along the route:** `poi_service.py` finds restaurants, cafés, malls and attractions near the route via
  Overpass, ranks them (documentation level + closeness, spread along the journey), shows roughly when you would pass each
  one, adapts to breakfast / lunch / snacks / dinner, marks them on the map and lets you add one as a stop (map mode).
- Bookings now also store the trip date/time; the weather label records the auto-detected condition.
- 27 new tests (51 total) plus mocked end-to-end app scenarios.

## Update: professional redesign ("FareCompass")
- New brand (`branding.py`), light theme (`.streamlit/config.toml`) and a custom navy/amber interface (`ui_components.py`):
  header bar with time and weather, step-by-step planner, ride-option cards, trip summary, weather & conditions tiles.
- Map-only trip selection that opens immediately (hubs / custom-coordinate modes removed), search boxes, per-point remove
  buttons, stray clicks no longer reset a finished route, and a stale-click bug after "Reset trip" is fixed.
- Plain-language labels throughout (Plan your ride, Ride options, Along your route, Save this trip, My trips).
- Removed the project-report / viva tab and all machine-learning wording; the fare estimate is shown as "FareCompass Estimate".
- Weather now shows temperature, feels-like, rain, wind, humidity and a next-hours outlook with icons.
- Footer disclaimer (estimates only, not affiliated with Ola/Uber/Rapido); all external text is HTML-escaped.

## Fix: map showed "API KEY REQUIRED"
- The CARTO tile URL now requires a key. Default is now OpenStreetMap's keyless standard tiles (softened with a CSS filter); tile source is configurable via `MAP_TILE_URL` / `MAP_TILE_ATTR`.

## Restored: performance results
- New **Performance** tab shows R², MAE, RMSE, MAPE, the actual-vs-predicted graph, feature importance, cross-validation and error by distance band, with an honest note that the data is simulated.
