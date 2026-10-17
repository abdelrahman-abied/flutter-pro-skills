# flutter_weather

A weather app following the bloc library's architecture
(https://bloclibrary.dev/architecture/): presentation (blocs/cubits and
widgets) → business logic → repository → data provider.

- `lib/data/` — data provider: a thin client for the Open-Meteo API
- `lib/repository/` — `WeatherRepository`, which composes the data provider and
  exposes domain models
- `lib/weather/`, `lib/search/`, `lib/settings/`, `lib/theme/` — features, each
  with its bloc/cubit and its views
