import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin
import hashlib
import re

URL = "https://www.office.kobe-u.ac.jp/stdnt-examinavi/info/index.html"
OUTPUT = Path(__file__).parent / "kobe.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

# --------------------------------------------------
# 既存RSSを読み込む
# --------------------------------------------------

old_items = {}

if OUTPUT.exists():
    try:
        old_tree = ET.parse(OUTPUT)

        for item in old_tree.getroot().findall("./channel/item"):
            guid = item.findtext("guid", "")

            if guid:
                old_items[guid] = {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "description": item.findtext("description", ""),
                    "pubDate": item.findtext("pubDate", ""),
                    "guid": guid,
                }

    except Exception:
        old_items = {}

# --------------------------------------------------
# ページ取得
# --------------------------------------------------

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()
response.encoding = response.apparent_encoding

soup = BeautifulSoup(
    response.text,
    "html.parser"
)

date_pattern = re.compile(
    r"^\s*(\d{4})\.(\d{2})\.(\d{2})\s*$"
)

categories = {
    "イベント",
    "ニュース",
    "入試情報",
}

current_items = []
seen_guids = set()

# --------------------------------------------------
# 各日付を基準に記事を取得
# --------------------------------------------------

date_nodes = soup.find_all(
    string=date_pattern
)

for date_node in date_nodes:

    match = date_pattern.match(
        date_node.strip()
    )

    if not match:
        continue

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))

    # 日付を含む項目全体を探す
    container = date_node.find_parent("li")

    if container is None:
        continue

    links = container.find_all(
        "a",
        href=True
    )

    category = ""
    article_link = None
    title = None

    for a in links:

        text = a.get_text(
            " ",
            strip=True
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        if not text:
            continue

        # 分類リンク
        if text in categories:
            category = text
            continue

        # 「令和○年度入試」などの補助分類は飛ばす
        if (
            "年度入試" in text
            and "について" not in text
        ):
            continue

        href = urljoin(
            URL,
            a["href"]
        )

        # 最後に残ったリンクを記事タイトルとして扱う
        title = text
        article_link = href

    if not title or not article_link:
        continue

    # 分類が取れなかった場合
    if not category:
        category = "News / Information"

    # URL＋日付＋タイトルからGUID作成
    # 同じリンク先を別の更新で再利用する場合にも対応
    guid_source = (
        f"{year}-{month:02d}-{day:02d}|"
        f"{title}|"
        f"{article_link}"
    )

    guid = hashlib.sha256(
        guid_source.encode("utf-8")
    ).hexdigest()

    if guid in seen_guids:
        continue

    seen_guids.add(guid)

    pub_date = datetime(
        year,
        month,
        day,
        12,
        0,
        0,
        tzinfo=JST
    )

    current_items.append({
        "title": title,
        "link": article_link,
        "description": f"分類：{category}",
        "pubDate": format_datetime(pub_date),
        "guid": guid,
    })

# --------------------------------------------------
# 既存RSSの記事も残す
# --------------------------------------------------

all_items = []
all_guids = set()

for item in current_items:

    if item["guid"] not in all_guids:
        all_items.append(item)
        all_guids.add(item["guid"])

for guid, item in old_items.items():

    if guid not in all_guids:
        all_items.append(item)
        all_guids.add(guid)

# --------------------------------------------------
# 新しい順
# --------------------------------------------------

def get_date(item):

    try:
        return parsedate_to_datetime(
            item["pubDate"]
        )

    except Exception:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

all_items.sort(
    key=get_date,
    reverse=True
)

all_items = all_items[:300]

# --------------------------------------------------
# RSS作成
# --------------------------------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)

ET.SubElement(
    channel,
    "title"
).text = "神戸大学受験生ナビ News / Information"

ET.SubElement(
    channel,
    "link"
).text = URL

ET.SubElement(
    channel,
    "description"
).text = (
    "神戸大学受験生ナビの"
    "News / Information新着情報"
)

ET.SubElement(
    channel,
    "language"
).text = "ja"

# --------------------------------------------------
# RSS記事
# --------------------------------------------------

for item in all_items:

    element = ET.SubElement(
        channel,
        "item"
    )

    ET.SubElement(
        element,
        "title"
    ).text = item["title"]

    ET.SubElement(
        element,
        "link"
    ).text = item["link"]

    ET.SubElement(
        element,
        "description"
    ).text = item["description"]

    ET.SubElement(
        element,
        "pubDate"
    ).text = item["pubDate"]

    guid_element = ET.SubElement(
        element,
        "guid"
    )

    guid_element.set(
        "isPermaLink",
        "false"
    )

    guid_element.text = item["guid"]

# --------------------------------------------------
# XML保存
# --------------------------------------------------

tree = ET.ElementTree(rss)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)

# --------------------------------------------------
# 結果表示
# --------------------------------------------------

print("RSS作成成功")
print(
    "今回取得:",
    len(current_items),
    "件"
)
print(
    "RSS保存件数:",
    len(all_items),
    "件"
)
print(
    "保存先:",
    OUTPUT
)

print()
print("最新15件:")

for item in current_items[:15]:

    print(
        item["pubDate"],
        item["description"],
        item["title"],
        "->",
        item["link"]
    )