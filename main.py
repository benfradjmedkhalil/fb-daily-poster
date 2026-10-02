import os, json, html, datetime, urllib.parse, requests, feedparser
from playwright.sync_api import sync_playwright

MODEL = "gemini-flash-latest"

LEAGUES = {
    "premier": dict(name="PREMIER LEAGUE", accent="#a855f7", lang="en",
                    query='"Premier League" when:1d'),
    "laliga": dict(name="LA LIGA", accent="#f97316", lang="en",
                   query='"La Liga" OR LaLiga when:1d'),
    "seriea": dict(name="SERIE A", accent="#22d3ee", lang="en",
                   query='"Serie A" football when:1d'),
    "bundesliga": dict(name="BUNDESLIGA", accent="#ef4444", lang="en",
                       query='Bundesliga when:1d'),
    "tunisia": dict(name="الرابطة المحترفة الأولى", accent="#22c55e", lang="ar",
                    query='"الرابطة المحترفة الأولى" OR "الدوري التونسي" when:2d'),
}

# Which league for which schedule (UTC cron lines in daily.yml)
SLOTS = {"0 7 * * *": "premier", "0 10 * * *": "laliga", "0 13 * * *": "tunisia",
         "0 16 * * *": "seriea", "0 19 * * *": "bundesliga"}

key = (SLOTS.get(os.environ.get("SCHEDULE", "").strip())
       or os.environ.get("LEAGUE_INPUT", "").strip() or "premier")
cfg = LEAGUES.get(key, LEAGUES["premier"])
ar = cfg["lang"] == "ar"
print("League:", key)

if ar:
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(cfg["query"]) + "&hl=ar&gl=TN&ceid=TN:ar"
else:
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(cfg["query"]) + "&hl=en&gl=US&ceid=US:en"

posted = json.load(open("posted.json"))
entry = next((e for e in feedparser.parse(url).entries if e.link not in posted), None)
if not entry:
    raise SystemExit("Nothing new for " + key)

if " - " in entry.title:
    title, source = entry.title.rsplit(" - ", 1)
else:
    title, source = entry.title, ""

# Caption
if ar:
    ask = ("Write a short Facebook caption in Arabic (Modern Standard Arabic, 2-3 sentences) "
           "for this football news headline, then add 3 relevant Arabic hashtags on a new line.")
else:
    ask = ("Write a short Facebook caption in English (2-3 sentences) for this football news "
           "headline, then add 3 relevant hashtags on a new line.")
prompt = f"{ask} Do not add any fact that is not in the headline. Output only the caption.\nHeadline: {title}"
try:
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        params={"key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
    caption = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
except Exception as ex:
    print("Gemini failed:", ex)
    caption = title
caption += ("\n\nالمصدر: " if ar else "\n\nSource: ") + (source or "link") + "\n" + entry.link

# Poster
n = len(title)
size = 84 if n < 55 else 72 if n < 85 else 62 if n < 120 else 52
if ar:
    size = int(size * 0.9)
vals = {
    "LANG": cfg["lang"], "DIR": "rtl" if ar else "ltr", "ACCENT": cfg["accent"],
    "LEAGUE": cfg["name"], "DATE": datetime.date.today().strftime("%d/%m/%Y"),
    "LABEL": "آخر الأخبار" if ar else "LATEST NEWS",
    "TITLE": html.escape(title), "SIZE": str(size),
    "LH": "1.4" if ar else "1.12",
    "FONT": "'Cairo',sans-serif" if ar else "'Oswald','Cairo',sans-serif",
    "WEIGHT": "900" if ar else "700",
    "TRANSFORM": "none" if ar else "uppercase",
    "SRCLABEL": "المصدر" if ar else "Source", "SOURCE": html.escape(source or "-"),
}
page_html = open("template.html", encoding="utf-8").read()
for k, v in vals.items():
    page_html = page_html.replace("{{" + k + "}}", v)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1080, "height": 1350})
    pg.set_content(page_html, wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(800)
    pg.screenshot(path="poster.png")
    b.close()

# Post to Facebook
res = requests.post(
    f"https://graph.facebook.com/v21.0/{os.environ['FB_PAGE_ID']}/photos",
    data={"caption": caption, "access_token": os.environ["FB_PAGE_TOKEN"]},
    files={"source": open("poster.png", "rb")}, timeout=60)
print(res.text)
res.raise_for_status()

posted.append(entry.link)
json.dump(posted[-300:], open("posted.json", "w"))
