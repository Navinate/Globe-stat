"""Build src/stats.json, src/centroids.json, src/schedule.json from OWID data in raw/.

Usage: python3 scripts/pipeline.py
"""
import json, math, random, re, sys, datetime as dt
from pathlib import Path
import pandas as pd
import pycountry

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OWD = RAW / "owd" / "datasets"
LIB = (ROOT / "node_modules/@lachlanjc/chlobe/dist/index.js").read_text()
MAX_YEAR = 2025
MIN_COVERAGE = 100
GH = "https://github.com/owid"

# ---------- globe countries + anchors (decoded from chlobe so distances match the globe) ----------
codes = re.search(r'ALPHA2_BY_COUNTRY_ID = "([^"]+)"', LIB).group(1)
anchors_b64 = re.search(r'COUNTRY_ANCHORS_BASE64 = "([^"]+)"', LIB).group(1)
W = int(re.search(r"ANCHOR_MAP_WIDTH = (\d+)", LIB).group(1))
H = int(re.search(r"ANCHOR_MAP_HEIGHT = (\d+)", LIB).group(1))
import base64
ab = base64.b64decode(anchors_b64)
CENTROIDS = {}
for cid in range(1, len(codes) // 2):
    a2 = codes[cid * 2: cid * 2 + 2]
    if a2 == "--":
        continue
    o = cid * 3
    cell = ab[o] + ab[o + 1] * 256 + ab[o + 2] * 65536
    lat = 90 - (cell // W + 0.5) / H * 180
    lon = (cell % W + 0.5) / W * 360 - 180
    CENTROIDS[a2] = [round(lat, 2), round(lon, 2)]
GLOBE = set(CENTROIDS) - {"AQ", "TF", "FK"}  # uninhabited / tiny territories that would win "least" prompts

# ---------- country name / iso3 -> alpha2 ----------
ALIASES = {
    "Bolivia": "BO", "Iran": "IR", "Russia": "RU", "South Korea": "KR", "North Korea": "KP", "Syria": "SY",
    "Laos": "LA", "Vietnam": "VN", "Tanzania": "TZ", "Venezuela": "VE", "Moldova": "MD", "Czechia": "CZ",
    "Czech Republic": "CZ", "Democratic Republic of Congo": "CD", "Democratic Republic of the Congo": "CD",
    "Congo": "CG", "Republic of the Congo": "CG", "Cote d'Ivoire": "CI", "Ivory Coast": "CI", "Macedonia": "MK",
    "North Macedonia": "MK", "Swaziland": "SZ", "Eswatini": "SZ", "Brunei": "BN", "Palestine": "PS",
    "Taiwan": "TW", "Kosovo": "XK", "Cape Verde": "CV", "East Timor": "TL", "Timor": "TL", "Micronesia": "FM",
    "Myanmar": "MM", "Burma": "MM", "Bahamas": "BS", "Gambia": "GM", "Falkland Islands": "FK",
    "Western Sahara": "EH", "Turkey": "TR", "United States": "US", "United Kingdom": "GB",
    "Slovak Republic": "SK", "Kyrgyz Republic": "KG", "Lao PDR": "LA", "Korea, Rep.": "KR",
    "Egypt, Arab Rep.": "EG", "Yemen, Rep.": "YE", "Somaliland": None, "Northern Cyprus": None,
}
_cache = {}
def to_a2(name):
    if name in _cache:
        return _cache[name]
    a2 = ALIASES.get(name, "")
    if a2 == "":
        c = pycountry.countries.get(name=name) or pycountry.countries.get(common_name=name) \
            or pycountry.countries.get(official_name=name)
        a2 = c.alpha_2 if c else None
    _cache[name] = a2
    return a2
def iso3_to_a2(code):
    if code == "OWID_KOS":
        return "XK"
    c = pycountry.countries.get(alpha_3=code) if isinstance(code, str) and len(code) == 3 else None
    return c.alpha_2 if c else None

# ---------- loaders: return {alpha2: (year, value)} using latest year per country ----------
def latest(df, key_col, keyfn, col, min_year, transform=None):
    d = df[[key_col, "year", col]].dropna()
    d = d[(d.year >= min_year) & (d.year <= MAX_YEAR)]
    out = {}
    for _, r in d.sort_values("year").iterrows():
        a2 = keyfn(r[key_col])
        if a2 in GLOBE:
            v = r[col]
            out[a2] = (int(r.year), float(transform(v) if transform else v))
    return out

_frames = {}
def frame(name):
    if name not in _frames:
        if name in ("co2", "energy"):
            _frames[name] = pd.read_csv(RAW / f"{name}.csv")
        elif name == "covid":
            d = pd.read_csv(RAW / "covid.csv")
            d["year"] = 2021  # static indicators in the latest file are mostly 2019-2021
            _frames[name] = d
        else:
            p = OWD / name / f"{name}.csv"
            d = pd.read_csv(p).rename(columns={"Year": "year"})
            _frames[name] = d
    return _frames[name]

SRC = {
    "co2": ("Our World in Data – CO₂ & GHG emissions", f"{GH}/co2-data"),
    "energy": ("Our World in Data – Energy", f"{GH}/energy-data"),
    "covid": ("Our World in Data (UN, World Bank & other sources via OWID COVID dataset)", f"{GH}/covid-19-data"),
}
SHORT = {
    "Human Height - NCD RisC (2017)": "NCD-RisC (2017) via Our World in Data",
    "World Happiness Report (2022)": "World Happiness Report 2022 via Our World in Data",
    "Corruption Perception Index - Transparency International (2018)": "Transparency International CPI via Our World in Data",
    "Daily supply of calories per person (OWID based on UN FAO & historical sources)": "UN FAO via Our World in Data",
    "Estimated average age at marriage, by gender (UN)": "UN via Our World in Data",
    "Prisoners per 100 000 from World Prison Brief (downloaded September 2018)_country_standardized": "World Prison Brief (2018) via Our World in Data",
    "SIPRI Military Expenditure Database": "SIPRI via Our World in Data",
    "Motor vehicles per 1000 people - NationMaster (2014)": "NationMaster (2014) via Our World in Data",
    "Forest land, deforestation and change (FAO, 2020)": "FAO (2020) via Our World in Data",
    "Fertility rate (Complete Gapminder, v12) (2017)": "Gapminder via Our World in Data",
    "Urban and rural population 1950-2050 - UN World Urbanization Prospects 2018": "UN World Urbanization Prospects via Our World in Data",
}
def owd_src(name):
    return (SHORT.get(name, f"Our World in Data – {name}"), f"{GH}/owid-datasets/tree/master/datasets/" + name.replace(" ", "%20"))

def S(id, source, col, unit, dec, most=None, least=None, tier=(2, 2), min_year=2012, log=False, transform=None):
    return dict(id=id, source=source, col=col, unit=unit, dec=dec, most=most, least=least, tier=tier,
                min_year=min_year, log=log, transform=transform)

HEIGHT = "Human Height - NCD RisC (2017)"
STATS = [
    # --- co2 ---
    S("co2pc", "co2", "co2_per_capita", "t CO₂/person", 1, "most CO₂ emissions per person", "least CO₂ emissions per person", (1, 3), log=True),
    S("methpc", "co2", "methane_per_capita", "t CO₂e/person", 1, "most methane emissions per person", None, (3, 0), log=True),
    S("energypc", "co2", "energy_per_capita", "kWh/person", 0, "highest energy use per person", "lowest energy use per person", (2, 3), log=True),
    # --- energy ---
    S("elecpc", "energy", "per_capita_electricity", "kWh/person", 0, "most electricity generated per person", None, (2, 0), log=True),
    S("nuclear", "energy", "nuclear_share_elec", "% of electricity", 1, "highest share of electricity from nuclear", None, (1, 0)),
    S("coal", "energy", "coal_share_elec", "% of electricity", 1, "highest share of electricity from coal", None, (2, 0)),
    S("solar", "energy", "solar_share_elec", "% of electricity", 1, "highest share of electricity from solar", None, (3, 0)),
    S("wind", "energy", "wind_share_elec", "% of electricity", 1, "highest share of electricity from wind", None, (2, 0)),
    S("hydro", "energy", "hydro_share_elec", "% of electricity", 1, "highest share of electricity from hydropower", None, (3, 0)),
    S("oilprod", "energy", "oil_prod_per_capita", "kWh/person", 0, "most oil produced per person", None, (2, 0), log=True),
    S("gasprod", "energy", "gas_prod_per_capita", "kWh/person", 0, "most natural gas produced per person", None, (2, 0), log=True),
    S("carbint", "energy", "carbon_intensity_elec", "g CO₂/kWh", 0, "dirtiest electricity (CO₂ per kWh)", "cleanest electricity (CO₂ per kWh)", (3, 2)),
    # --- covid-file static indicators ---
    S("pop", "covid", "population", "people", 0, "largest population", "smallest population", (1, 2), log=True),
    S("density", "covid", "population_density", "people/km²", 0, "highest population density", "lowest population density", (1, 2), log=True),
    S("medage", "covid", "median_age", "years", 1, "oldest population (median age)", "youngest population (median age)", (1, 2)),
    S("age65", "covid", "aged_65_older", "% of people", 1, "largest share of people aged 65+", None, (1, 0)),
    S("gdppc", "covid", "gdp_per_capita", "$/person (PPP)", 0, "highest GDP per person", "lowest GDP per person", (1, 2), log=True),
    S("diabetes", "covid", "diabetes_prevalence", "% of adults", 1, "highest diabetes prevalence", None, (3, 0)),
    S("fsmoke", "covid", "female_smokers", "% of women", 1, "highest share of women who smoke", None, (3, 0)),
    S("msmoke", "covid", "male_smokers", "% of men", 1, "highest share of men who smoke", None, (3, 0)),
    S("beds", "covid", "hospital_beds_per_thousand", "beds/1,000 people", 1, "most hospital beds per person", None, (2, 0)),
    S("lifeexp", "covid", "life_expectancy", "years", 1, "highest life expectancy", "lowest life expectancy", (1, 2)),
    S("hdi", "covid", "human_development_index", "HDI", 3, "highest Human Development Index", "lowest Human Development Index", (2, 2)),
    # --- owid-datasets archive ---
    S("mheight", HEIGHT, "Mean male height (cm)", "cm", 1, "tallest men", "shortest men", (1, 3), min_year=1990),
    S("fheight", HEIGHT, "Mean female height (cm)", "cm", 1, "tallest women", "shortest women", (2, 3), min_year=1990),
    S("happy", "World Happiness Report (2022)", "Life satisfaction in Cantril Ladder (World Happiness Report 2022)", "/10", 2, "happiest people (life satisfaction)", "least happy people (life satisfaction)", (1, 2)),
    S("cpi", "Corruption Perception Index - Transparency International (2018)", "Corruption Perception Index (Transparency International (2016))", "/100", 0, "least corruption (Corruption Perceptions Index)", "most corruption (Corruption Perceptions Index)", (2, 2)),
    S("calories", "Daily supply of calories per person (OWID based on UN FAO & historical sources)", "Daily caloric supply (OWID based on UN FAO & historical sources)", "kcal/day", 0, "most calories available per person", "fewest calories available per person", (2, 3)),
    S("marriage", "Crude marriage rate (OWID based on UN, OECD, Eurostat and other sources)", "Crude marriage rate (per 1,000 inhabitants)", "per 1,000 people", 1, "highest marriage rate", "lowest marriage rate", (3, 3), min_year=2005),
    S("wmarryage", "Estimated average age at marriage, by gender (UN)", "Estimated average age at marriage, women (UN)", "years", 1, "oldest average age at marriage for women", "youngest average age at marriage for women", (3, 2), min_year=2000),
    S("prison", "Prisoners per 100 000 from World Prison Brief (downloaded September 2018)_country_standardized", "Prison population rate (World Prison Brief 2018)", "per 100,000 people", 0, "highest incarceration rate", "lowest incarceration rate", (1, 3), min_year=2000),
    S("military", "SIPRI Military Expenditure Database", "military_expenditure_share_gdp", "% of GDP", 1, "highest military spending as a share of GDP", "lowest military spending as a share of GDP", (2, 3)),
    S("cars", "Motor vehicles per 1000 people - NationMaster (2014)", "Motor vehicles per 1000 people (NationMaster (2014))", "per 1,000 people", 0, "most motor vehicles per person", "fewest motor vehicles per person", (2, 3), min_year=2000),
    S("forest", "Forest land, deforestation and change (FAO, 2020)", "Forest cover", "% of land", 1, "highest share of land covered by forest", "lowest share of land covered by forest", (2, 2)),
    S("fertility", "Fertility rate (Complete Gapminder, v12) (2017)", "Fertility rate (Complete Gapminder, v12) (2017)", "births/woman", 2, "highest fertility rate", "lowest fertility rate", (1, 2), min_year=2015),
]

def urban_share():
    name = "Urban and rural population 1950-2050 - UN World Urbanization Prospects 2018"
    d = frame(name)
    u, r = d.columns[2], d.columns[3]
    d = d[d.year == 2020].copy()
    out = {}
    for _, row in d.iterrows():
        a2 = to_a2(row.Entity)
        if a2 in GLOBE and row[u] + row[r] > 0:
            out[a2] = (2020, float(100 * row[u] / (row[u] + row[r])))
    return out, owd_src(name)

def load_stat(s):
    src = s["source"]
    d = frame(src)
    if src in ("co2", "energy", "covid"):
        key, fn = "iso_code", iso3_to_a2
        source = SRC[src]
    else:
        key, fn = "Entity", to_a2
        source = owd_src(src)
    if src == "covid":
        d = d.rename(columns={})
    vals = latest(d, key, fn, s["col"], s["min_year"], s["transform"])
    return vals, source

def fmt_years(ys):
    lo, hi = min(ys), max(ys)
    mode = max(set(ys), key=ys.count)
    return str(hi) if lo == hi else f"{lo}–{hi} (mostly {mode})"

stats, prompts, report = [], [], []
entries = [(s, *load_stat(s)) for s in STATS]
us, usrc = urban_share()
entries.append((S("urban", None, None, "% of people", 1, "most urbanized population", "most rural population", (2, 2)), us, usrc))

for s, vals, (src_name, src_url) in entries:
    n = len(vals)
    if n < MIN_COVERAGE:
        report.append(f"DROP {s['id']}: coverage {n}")
        continue
    if s["source"] == HEIGHT:
        year = "adults born in 1996"
    elif s["source"] == "covid":
        year = "≈2019–2021"
    else:
        year = fmt_years([y for y, _ in vals.values()])
    values = {a: round(v, s["dec"] + 1) for a, (y, v) in vals.items()}
    stats.append(dict(id=s["id"], unit=s["unit"], dec=s["dec"], log=s["log"], year=year,
                      source=src_name, url=src_url, values=values))
    for direction, label, tier in (("most", s["most"], s["tier"][0]), ("least", s["least"], s["tier"][1])):
        if not label:
            continue
        order = sorted(values.items(), key=lambda kv: -kv[1] if direction == "most" else kv[1])
        if order[0][1] == order[1][1]:  # ambiguous #1
            report.append(f"DROP {s['id']}-{direction}: tie at top {order[:3]}")
            continue
        prompts.append(dict(id=f"{s['id']}-{direction}", stat=s["id"], dir=direction, label=label, tier=tier,
                            top=[a for a, _ in order[:3]]))
    report.append(f"ok   {s['id']:10} n={n:3} year={year}")

# ---------- schedule: day N -> [tier1, tier2, tier3] prompts, distinct stats per day ----------
START = dt.date(2026, 11, 16)
DAYS = 365
rng = random.Random(20261116)
pools = {t: [p["id"] for p in prompts if p["tier"] == t] for t in (1, 2, 3)}
queues = {t: [] for t in pools}
stat_of = {p["id"]: p["stat"] for p in prompts}
schedule = {}
for day in range(DAYS):
    picks, used = [], set()
    for t in (1, 2, 3):
        if not queues[t]:
            q = pools[t][:]; rng.shuffle(q); queues[t] = q
        # take the first prompt whose stat isn't already used today
        i = next((i for i, pid in enumerate(queues[t]) if stat_of[pid] not in used), 0)
        pid = queues[t].pop(i)
        picks.append(pid); used.add(stat_of[pid])
    schedule[(START + dt.timedelta(days=day)).isoformat()] = picks

out = ROOT / "src"
(out / "stats.json").write_text(json.dumps(dict(stats=stats, prompts=prompts), ensure_ascii=False, separators=(",", ":")))
(out / "centroids.json").write_text(json.dumps(CENTROIDS, separators=(",", ":")))
(out / "schedule.json").write_text(json.dumps(dict(start=START.isoformat(), days=schedule), separators=(",", ":")))
print("\n".join(report))
print(f"stats={len(stats)} prompts={len(prompts)} tiers={ {t: len(v) for t, v in pools.items()} }")
print("unmatched names:", sorted(k for k, v in _cache.items() if v is None and not re.search(r"\(|World|income|Africa|Asia|Europe|America|Oceania|countries|Union|region|OECD|Caribbean|states", k))[:60])
