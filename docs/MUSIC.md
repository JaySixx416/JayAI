# Song Studio — 0.25.0

Song Studio runs in the JayAI dashboard on Linux. Open **Song Studio** from the dashboard rail, enter the current dashboard key, add a concept and/or draft lyrics, and select a revision level. Click **Run studio review** to request a structured package containing the song's underlying message, strengths, audit findings, revised master, best lines, performance map, title options, and Suno style/exclude text.

## Chromebook setup

Song Studio uses the OpenAI Chat Completions API. It is optional; Linux health features continue to work without it. Create an API key in your OpenAI developer account, then enter it into the Linux shell without echoing it or putting it in shell history:

```bash
cd ~/JayAI-CrossDevice-0.25.0
read -s -p 'OpenAI API key: ' JAYAI_MUSIC_API_KEY; echo
export JAYAI_MUSIC_API_KEY
export JAYAI_MUSIC_MODEL=gpt-4.1-mini
./scripts/start-jayai.sh
```

Keep that terminal open while using JayAI. The key is held in the server process environment; JayAI does not write it to the database or log it. Starting a new terminal session requires entering it again. The model name can be changed with `JAYAI_MUSIC_MODEL` to another model available to the account. A ChatGPT subscription does not include API usage; API usage can incur separate charges.

When you click **Run studio review**, the submitted title, concept, lyrics, and style direction are sent to OpenAI's API for processing. Do not submit material you do not want sent to that provider. JayAI does not automatically save the song package; download the returned JSON if you want to retain it. The dashboard key is held in the browser tab only and is not stored in browser storage.

## Suno handoff

Use the copy buttons for the title, final lyrics, style prompt (limited to 750 characters), and exclude prompt. Review the content, then paste it into Suno Custom Mode yourself. JayAI does not log in to, automate, scrape, or press Create on Suno. No official public Suno API was verified for this release. This avoids relying on an unofficial endpoint or automating the website.

The generation itself remains under the user's control in Suno. Keep the downloaded JSON with any chosen audio and generation records if you need a local project note; the JSON is a writing package, not proof of Suno generation or commercial-use rights.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Song Studio says model not configured | Start JayAI from a terminal where `JAYAI_MUSIC_API_KEY` is set. |
| HTTP 401 or 403 from provider | Check API key validity, account API access, and billing status. The key is not shown back in the error. |
| Model not found or unsupported | Set `JAYAI_MUSIC_MODEL` to a model available to the API account, then restart JayAI. |
| Slow or invalid response | Try a shorter draft; the request has a four-minute timeout. |
| Chromebook cannot open Song Studio | Open `http://localhost:8000/music` while the Linux launcher is running. |

