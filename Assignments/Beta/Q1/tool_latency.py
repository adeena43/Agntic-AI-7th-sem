"""
tool_latency.py: measures the four tool delays required by Question 1 (Section 2, item 6).

Run this on your own machine (the sandbox used to prepare this package had no outbound access to
Open-Meteo or OpenAQ, so NO measurements were taken there; tool_latency_log_TEMPLATE.csv is empty by design).

Usage:
    pip install requests
    export OPENAQ_API_KEY=your_key        # OpenAQ v3 needs a free API key (https://explore.openaq.org)
    python tool_latency.py --day-label day1      # run once on day 1 (20+ calls per API)
    python tool_latency.py --day-label day2      # run again on a different calendar day
    python tool_latency.py --summarise           # prints medians over all rows of tool_latency_log.csv

Each run appends rows to tool_latency_log.csv with a UTC timestamp. The assignment asks for at least 20 calls
to each API spread over at least two days; the default is 12 calls per run so two runs give 24 per API.
"""
import argparse, csv, os, statistics, sys, time, datetime, math

try:
    import requests
except ImportError:
    requests = None

LOG = "tool_latency_log.csv"
FIELDS = ["utc_timestamp", "day_label", "component", "run", "latency_s", "status"]
KARACHI = (24.8607, 67.0011)

def timed(fn):
    t0 = time.perf_counter()
    try:
        fn()
        return time.perf_counter() - t0, "ok"
    except Exception as e:                      # record failures instead of hiding them
        return time.perf_counter() - t0, f"error:{type(e).__name__}"

def call_weather():
    lat, lon = KARACHI
    r = requests.get("https://api.open-meteo.com/v1/forecast",
                     params={"latitude": lat, "longitude": lon,
                             "current": "temperature_2m,relative_humidity_2m,wind_speed_10m"}, timeout=15)
    r.raise_for_status(); r.json()

def call_airquality():
    key = os.environ.get("OPENAQ_API_KEY")
    if not key:
        raise RuntimeError("OPENAQ_API_KEY not set")
    lat, lon = KARACHI
    r = requests.get("https://api.openaq.org/v3/locations",
                     params={"coordinates": f"{lat},{lon}", "radius": 25000, "limit": 5},
                     headers={"X-API-Key": key}, timeout=15)
    r.raise_for_status(); r.json()

def heat_index_c(temp_c, rh):
    """Rothfusz regression (NWS) in Fahrenheit, converted back to Celsius."""
    t = temp_c*9/5 + 32
    if t < 80:
        hi = 0.5*(t + 61.0 + (t-68.0)*1.2 + rh*0.094)
    else:
        hi = (-42.379 + 2.04901523*t + 10.14333127*rh - 0.22475541*t*rh - 6.83783e-3*t*t
              - 5.481717e-2*rh*rh + 1.22874e-3*t*t*rh + 8.5282e-4*t*rh*rh - 1.99e-6*t*t*rh*rh)
    return (hi-32)*5/9

# Small stand-in knowledge base: replace with your real retrieval step (e.g. a vector or keyword index).
KB = [
 "Heatwave advisory: avoid outdoor work between 12:00 and 16:00; drink water regularly.",
 "Children and the elderly should stay indoors when the heat index is above 41 C.",
 "PM2.5 above 150 ug/m3: asthma patients should avoid outdoor exercise and wear a N95 mask.",
 "Outdoor labourers should take shade breaks every hour during heatwaves.",
]
def call_kb():
    q = set("is it safe evening jog sea heat children".split())
    max(KB, key=lambda d: len(q & set(d.lower().split())))

def call_heat_index():
    heat_index_c(36.0, 62.0)

def run(day_label, n):
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(FIELDS)
        jobs = [("openmeteo_weather", call_weather, n, True), ("openaq_airquality", call_airquality, n, True),
                ("heat_index_local", call_heat_index, n, False), ("kb_lookup_local", call_kb, n, False)]
        for comp, fn, reps, net in jobs:
            if net and requests is None:
                print("install requests first"); sys.exit(1)
            for i in range(1, reps+1):
                # local calls take microseconds, so time 1000 repetitions and divide
                if net:
                    dt, st = timed(fn)
                else:
                    t0 = time.perf_counter()
                    for _ in range(1000): fn()
                    dt, st = (time.perf_counter()-t0)/1000, "ok"
                w.writerow([datetime.datetime.now(datetime.timezone.utc).isoformat(), day_label, comp, i, f"{dt:.6f}", st])
                if net: time.sleep(1.0)
    print("appended to", LOG)

def summarise():
    rows = list(csv.DictReader(open(LOG)))
    ok = [r for r in rows if r["status"] == "ok"]
    by = {}
    for r in ok: by.setdefault(r["component"], []).append(float(r["latency_s"]))
    for c, v in by.items():
        days = {r["day_label"] for r in ok if r["component"] == c}
        print(f"{c:20s} n={len(v):3d} days={len(days)} median={statistics.median(v):.4f}s")
    allv = [float(r["latency_s"]) for r in ok]
    print("median over all measurements (assignment's single tool delay):", round(statistics.median(allv), 4), "s")
    print("note: the pooled median is dominated by the many fast local rows if you collect equal counts; report the per-component medians too.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--day-label", default="day1")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--summarise", action="store_true")
    a = ap.parse_args()
    summarise() if a.summarise else run(a.day_label, a.n)
