import re, os
from flask import Flask, Response
import requests
from bs4 import BeautifulSoup
import concurrent.futures

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_FILE = os.path.join(BASE_DIR, "backup.txt")

CAT_ORDER = ["Chroma", "Unique", "Ancient", "Godly", "Vintage", "Legendary", "Rare", "Uncommon", "Common"]
CAT_MAP = {
    "common":    "Common", 
    "uncommon":  "Uncommon", 
    "rare":      "Rare",
    "legendary": "Legendary", 
    "godly":     "Godly", 
    "ancient":   "Ancient",
    "unique":    "Unique", 
    "classic":   "Vintage", 
    "chroma":    "Chroma"
}
CATEGORIES = {
    "common":    "https://supremevalues.com/mm2/commons",
    "uncommon":  "https://supremevalues.com/mm2/uncommons",
    "rare":      "https://supremevalues.com/mm2/rares",
    "legendary": "https://supremevalues.com/mm2/legendaries",
    "godly":     "https://supremevalues.com/mm2/godlies",
    "ancient":   "https://supremevalues.com/mm2/ancients",
    "unique":    "https://supremevalues.com/mm2/uniques",
    "classic":   "https://supremevalues.com/mm2/vintages",
    "chroma":    "https://supremevalues.com/mm2/chromas"
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


def parse_special_value(text):
    text = text.strip()
    match = re.search(r'(?:X|x)?\s?([\d\.]+)', text)
    if not match:
        return None
    val = float(match.group(1))
    if "T1 Legendaries" in text: return val * 0.2
    elif "T1 Rares" in text:     return val * 0.1
    elif "T1 Uncommons" in text: return val * 0.05
    elif "T1 Common" in text:    return val * 0.025
    return val


def fetch_category(rarity_key, url):
    items = {}
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return rarity_key, None
        soup = BeautifulSoup(res.text, 'html.parser')
        heads  = soup.find_all(class_='itemhead')
        bodies = soup.find_all(class_='itembody')
        for head, body in zip(heads, bodies):
            name = head.get_text(separator=" ").split(" Click ")[0].strip()
            if rarity_key == "chroma":
                name = re.sub(r'^(Chroma|C\.)\s+', '', name, flags=re.IGNORECASE)
            val_tag = body.find('b', class_='itemvalue')
            if val_tag:
                raw_text = val_tag.get_text().strip()
                if rarity_key in ["common", "uncommon", "rare", "legendary"]:
                    final_val = parse_special_value(raw_text)
                else:
                    num_str = "".join(c for c in raw_text if c.isdigit() or c == '.')
                    final_val = float(num_str) if num_str else None
                if final_val is not None:
                    items[name] = int(final_val) if float(final_val).is_integer() else round(final_val, 4)
    except Exception:
        return rarity_key, None
    return rarity_key, items


def build_lua(results):
    lua = "return {\n"
    for cat in CAT_ORDER:
        items = results.get(cat) or {}
        lua += f"    {cat} = {{\n"
        sorted_items = sorted(items.items(), key=lambda x: (-x[1], x[0]))
        rows = [f'        ["{n.replace(chr(34), chr(92)+chr(34))}"] = {v}' for n, v in sorted_items]
        lua += ",\n".join(rows) + "\n    },\n"
    lua = lua.rstrip(",\n") + "\n}"
    return lua


@app.route('/')
def get_lua_table():
    results = {}
    failed_categories = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
        futures = {executor.submit(fetch_category, k, v): k for k, v in CATEGORIES.items()}
        for future in concurrent.futures.as_completed(futures):
            key, data = future.result()
            if data is None or len(data) == 0:
                failed_categories.append(key)
            results[CAT_MAP[key]] = data

    if failed_categories and os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype='text/plain')

    lua_output = build_lua(results)

    if not failed_categories:
        try:
            with open(BACKUP_FILE, "w", encoding="utf-8") as f:
                f.write(lua_output)
        except OSError as e:
            app.logger.warning(f"Could not write backup: {e}")
    return Response(lua_output, mimetype='text/plain')


@app.route('/backup')
def get_only_backup():
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content, mimetype="text/plain",
            headers={"Content-Disposition": "inline"})
    except FileNotFoundError:
        return "return 'nub'", 404
