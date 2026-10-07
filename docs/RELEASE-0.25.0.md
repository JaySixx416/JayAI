# Release 0.25.0

Adds a browser-based Song Studio to the self-hosted dashboard, packaged for Chromebook Crostini and Windows.

- Adds authenticated `/music` UI, `/api/music/status`, and `/api/music/prepare` endpoints.
- Calls the OpenAI Chat Completions API only when the user submits a studio review; the API key is read from `JAYAI_MUSIC_API_KEY` and is not persisted by JayAI.
- Returns a validated review package with title options, song analysis, audit findings, revised lyrics, best lines, performance map, and a Suno style prompt capped at 750 characters.
- Adds copy controls and JSON export for the result.
- Leaves Suno creation manual; this release does not automate Suno's website and has no verified Suno public API integration.
- No database migration; existing PostgreSQL data is unchanged.

Automated tests cover request bounds, required inputs, model response validation, prompt-length checks, provider error handling, authentication, and Chromebook UI availability. Actual Chromebook browser use and live OpenAI API calls require verification on the user's device/account.
