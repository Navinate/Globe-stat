# Globe Stats

A daily geography game: 3 prompts a day ("tap the country with the highest life expectancy"), played on a
[chlobe](https://chlobe.lachlanjc.com/) globe and scored by distance, like MapTap.

## Run

```sh
npm install
npm run dev      # local dev
npm run build    # dist/index.html — one self-contained file
```

## Deploy (Vercel)

Import the repo in Vercel; `vercel.json` sets the Vite build (`npm run build` → `dist/`). Or run `npx vercel --prod`.

```sh
```

## Data

`npm run data` (`scripts/pipeline.py`, needs `pandas` + `pycountry`) reads OWID CSVs from `raw/` and writes:

- `src/stats.json`: 35 indicators, keeping each country's most recent value. Countries are limited to those on the chlobe globe, and a stat needs at least 100 countries. Each stat also has its prompts (most/least, label, difficulty tier, top 3).
- `src/schedule.json`: 365 days of prompts from 2026-11-16. Rounds go easy → medium → hard, there are no repeats until a tier's pool runs out, and no stat appears twice in a day. After the schedule ends, prompts are picked using the date as a seed.
- `src/centroids.json`: country anchor points decoded from chlobe, so distances match what's drawn on the globe.

To fetch `raw/`:

```sh
mkdir -p raw && cd raw
curl -O https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv && mv owid-co2-data.csv co2.csv
curl -O https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv && mv owid-energy-data.csv energy.csv
curl -o covid.csv https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/latest/owid-covid-latest.csv
git clone --depth 1 --filter=blob:none --sparse https://github.com/owid/owid-datasets owd   # then sparse-checkout the datasets named in pipeline.py
```

Add a stat by appending an `S(...)` line in `pipeline.py`. A prompt is dropped automatically if #1 is tied.

## Scoring (`src/game.js`)

`score = max over the top 3 of cap × (1 − km/8000)^1.5`, where the caps are 100 / 95 / 90 for #1 / #2 / #3. So landing on #1 scores 100, a neighbor of the answer still scores well, and anything 8,000 km or more away scores 0.
To score against #1 only, set `CAPS = [100]` and use `prompt.top.slice(0, 1)`.

## Notes

- chlobe has no click event, so `useTap` in `main.jsx` turns a short tap into a synthetic `pointermove` to hit-test the country.
- Progress and streaks are stored in localStorage.
