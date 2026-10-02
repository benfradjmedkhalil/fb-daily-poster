import os, json, datetime, requests, feedparser
from playwright.sync_api import sync_playwright

FEED = "https://news.google.com/rss/search?q=football&hl=en&gl=US&ceid=US:en"
MODEL = "gemini-flash-latest"

posted = json.load(open("posted.json"))
entry = next((e for e in feedparser.parse(FEED).entries if e.link not in posted), None)
if not entry:
    raise SystemExit("Nothing new")

title, _, source = entry.title.rpartition(" - ")
title = title or entry.title

prompt = (f"Write a short Facebook caption (max 3 sentences, English) for this headline. "
          f"Do not add any fact that is not in the headline.\nHeadline: {title}")
r = requests.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
    params={"key": os.environ["GEMINI_API_KEY"]},
    json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
caption = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
caption += f"\n\nSource: {source or 'see link'}\n{entry.link}"

html = (open("template.html", encoding="utf-8").read()
        .replace("{{TITLE}}", title).replace("{{SOURCE}}", source or "")
        .replace("{{DATE}}", datetime.date.today().strftime("%d/%m/%Y")))
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1080, "height": 1350})
    pg.set_content(html)
    pg.screenshot(path="poster.png")
    b.close()

res = requests.post(
    f"https://graph.facebook.com/v21.0/{os.environ['FB_PAGE_ID']}/photos",
    data={"caption": caption, "access_token": os.environ["FB_PAGE_TOKEN"]},
    files={"source": open("poster.png", "rb")}, timeout=60)
print(res.text)
res.raise_for_status()

posted.append(entry.link)
json.dump(posted[-200:], open("posted.json", "w"))
