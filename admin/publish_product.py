# -*- coding: utf-8 -*-
"""publish_product.py — полный цикл публикации товара из Directus на сайт.

Что делает один вызов:
  1. читает товар из Directus (коллекция products + галерея gallery);
  2. собирает страницу /<slug>.html по эталонному Tilda-шаблону
     women-tshirt-letuchka.html: те же блоки (t989 галерея, t180/T165 карточка,
     t050+t165 FAQ, подвал с WhatsApp) и те же защитные проверки, что в
     _scripts/build_product_pages.js;
  3. обновляет sitemap.xml (loc, lastmod, priority, image:image);
  4. дописывает/обновляет модель в llms.txt и llms-full.txt;
  5. пишет отчёт в reports/product-publish.jsonl.

Ручные страницы не затираются. Страница считается «своей», если в ней есть
маркер <!-- jnn:publish ... -->. Файл без маркера перезаписывается только
с force=True.

Видимость: товар с show_in_catalog=false публикуется как черновик —
meta robots "noindex, follow", без записи в sitemap и llms.

CLI (на VPS из /var/www/jnnfactory):
  venv/bin/python -m admin.publish_product --list
  venv/bin/python -m admin.publish_product --slug kurtka-bomber
  venv/bin/python -m admin.publish_product --slug kurtka-bomber --dry
  venv/bin/python -m admin.publish_product --slug kurtka-bomber --force
  venv/bin/python -m admin.publish_product --sync
  venv/bin/python -m admin.publish_product --all-missing
  venv/bin/python -m admin.publish_product --unpublish kurtka-bomber

API (админка; nginx проксирует /gallery-api/ на порт 5000):
  GET  /gallery-api/publish/status
  POST /gallery-api/publish    {"slug": "..."} | {"sync": true} | {"all_missing": true}
  POST /gallery-api/unpublish  {"slug": "..."}
  GET  /gallery-api/publish/log?limit=20
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html as html_mod
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

VERSION = "2026-10-17.1"

SITE = (os.environ.get("JNN_SITE_URL") or "https://jnnfactory.online").rstrip("/")
SITE_ROOT = (os.environ.get("JNN_SITE_ROOT") or "/var/www/jnnfactory").rstrip("/\\")
DIRECTUS = (os.environ.get("JNN_DIRECTUS_URL") or "http://127.0.0.1:8055").rstrip("/")

# Эталон вёрстки — отдельный файл, а не живая страница товара: страница-эталон
# сама перезаписывается публикатором, и если читать шаблон из неё, второй прогон
# не находит исходных подстрок (title/h1/FAQ эталона). Каталог admin/ закрыт
# в nginx (return 404), поэтому шаблон наружу не отдаётся.
TEMPLATE_DIR = os.path.join("admin", "templates")
TEMPLATE_NAME = "product.html"
TEMPLATE_SLUG = "women-tshirt-letuchka"
TEMPLATE_H1 = "Футболка «Летучка»"
CANON_MIN_ORDER = "Минимальная партия под заказ (СТМ): от 500 шт. Готовые модели со склада: от 50 шт."
WHATSAPP = "wa.me/996700712212"
MARKER_PREFIX = "<!-- jnn:publish"
PAGE_PRIORITY = "0.8"
LOG_NAME = os.path.join("reports", "product-publish.jsonl")

GRID_START = ('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));'
              'gap:8px;padding:12px;background:#f5f5f5;">')
GRID_END = "<!--/gallery -->"

SPEC_LABELS = {"fabric": "Ткань", "composition": "Состав", "density": "Плотность", "sizes": "Размеры"}

# FAQ — те же ответы, что на уже опубликованных товарных страницах (вельвет/костюм).
FAQ_TEMPLATE = [
    ("Какой минимальный заказ?",
     "Готовые модели со склада - от 50 шт. Пошив в другом цвете или из другой ткани - от 500 шт на модель и цвет."),
    ("Можно ли нанести свой принт или вышивку?",
     "Да, у нас свой печатный цех M&R (до 12 цветов). Поддерживаем шелкографию, DTG, термотрансфер. "
     "Пришлите макет - проверим и сделаем тестовую печать."),
    ("Какие размеры доступны?", "{sizes_line} При заказе от 500 шт можем добавить размеры по вашей размерной сетке."),
    ("Можно ли сшить модель из другой ткани или другого кроя?",
     "Да, это модель СТМ: подберём ткань по плотности и составу, разработаем или повторим лекала, подберём "
     "фурнитуру. Партия от 500 шт."),
    ("Сроки производства?",
     "Готовые модели - отгрузка 1-3 дня. СТМ / кастомные цвета - 7-14 рабочих дней после утверждения образца."),
    ("Как оформляется заказ?",
     "1) Присылаете запрос → 2) Присылаем прайс и условия → 3) Утверждаете образец (если СТМ) → "
     "4) Предоплата 65% → 5) Производство → 6) Остаток 35% перед отгрузкой."),
    ("Доставка в Россию и Казахстан?",
     "Да, отправляем карго. Доставка Москва 5-12 дней, стоимость от 40 руб./кг."),
]

GENDER_TAIL = re.compile(
    r"^(?P<base>.+?)\s+(?:женская|женское|женский|мужская|мужское|мужской|унисекс|для\s+женщин|для\s+мужчин)$",
    re.IGNORECASE)


class PublishError(Exception):
    """Ошибка публикации: товар не найден, шаблон изменился, нет фото и т.п."""


# ---------------------------------------------------------------------------
# файлы и HTTP
# ---------------------------------------------------------------------------

def read_text(path: str, limit: int | None = None) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(limit) if limit else f.read()


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read_head(path: str, limit: int = 8192) -> str:
    """Первые килобайты файла — этого достаточно, чтобы увидеть маркер публикации."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(limit)


def http_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "jnn-publish/" + VERSION,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PublishError(f"Directus ответил {exc.code} на {url}") from None
    except Exception as exc:  # noqa: BLE001 — нужен понятный текст наверх
        raise PublishError(f"Directus недоступен ({exc}): {url}") from None


# ---------------------------------------------------------------------------
# данные Directus
# ---------------------------------------------------------------------------

def fetch_products() -> list[dict]:
    """Все товары с галереями (поля берём целиком — схема может меняться).

    Галерея товара — M2M-поле products.gallery (junction products_files -> directus_files).
    Резерв: старое имя gallery_files и текстовое gallery_urls — на случай отката схемы.
    """
    for fields in ("*,gallery.*", "*,gallery_files.*"):
        query = urllib.parse.urlencode({"limit": 500, "fields": fields, "sort": "sort"})
        try:
            payload = http_json(f"{DIRECTUS}/items/products?{query}")
        except PublishError:
            continue
        return payload.get("data") or []
    return []


def slug_of(product: dict) -> str:
    return text_of(product.get("slug")).strip("/ ")


def sku_of(product: dict) -> str:
    return text_of(product.get("code")).split(" · ")[0].strip()


def text_of(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def price_of(product: dict) -> str:
    value = product.get("price")
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return ""


def photos_of(product: dict) -> list[str]:
    """Фото товара: M2M-галерея (сначала gallery, затем старое имя gallery_files),
    порядок по полю sort, иначе — поле image."""
    rows = []
    gallery = []
    for key in ("gallery", "gallery_files"):
        value = product.get(key)
        if isinstance(value, list) and value:
            gallery = value
            break
    for index, row in enumerate(gallery):
        if isinstance(row, str):
            # старый формат: прямые ссылки вида /assets/... в поле gallery_urls
            if row.startswith(("http", "/")):
                rows.append((index, index, row))
            continue
        if not isinstance(row, dict):
            continue
        file_id = row.get("directus_files_id", row.get("id"))
        if isinstance(file_id, dict):
            file_id = file_id.get("id")
        if not file_id:
            continue
        try:
            order = int(row.get("sort"))
        except (TypeError, ValueError):
            order = index
        rows.append((order, index, f"/assets/{file_id}"))
    rows.sort()
    photos = [value for _, _, value in rows]
    if not photos:
        image = text_of(product.get("image")).strip()
        if image:
            photos = [image if image.startswith(("http", "/")) else "/" + image]
    return photos


def parse_specs(product: dict) -> dict:
    """Характеристики товара: строки в порядке заполнения (bullets важнее полей)."""
    values = {"fabric": "", "composition": "", "density": "", "sizes": ""}
    lines: list[tuple[str, str]] = []

    def add(kind: str, value: str) -> None:
        value = text_of(value).strip()
        if not value:
            return
        if kind in values:
            values[kind] = value
        lines.append((kind, value))

    add("fabric", text_of(product.get("fabric")))
    composition_density = text_of(product.get("composition_density")).strip()
    if composition_density:
        for part in [x.strip() for x in re.split(r"[·|]", composition_density) if x.strip()]:
            add("density" if re.search(r"г\s*/\s*м", part) else "composition", part)
    add("sizes", text_of(product.get("sizes")))

    bullets = text_of(product.get("bullets")).strip()
    if bullets:
        values = {"fabric": "", "composition": "", "density": "", "sizes": ""}
        lines = []
        kinds = {"ткань": "fabric", "состав": "composition", "плотность": "density",
                 "размеры": "sizes", "размер": "sizes"}
        for raw in re.split(r"[\r\n]+", bullets):
            line = raw.strip().lstrip("•·*–— ").strip()
            if not line:
                continue
            match = re.match(r"^(ткань|состав|плотность|размеры|размер)\s*:\s*(.+)$", line, re.IGNORECASE)
            if not match:
                add("other", line)
                continue
            kind = kinds[match.group(1).lower()]
            value = line.split(":", 1)[1].strip()
            if kind == "composition":
                for part in [x.strip() for x in re.split(r"[·|]", value) if x.strip()]:
                    add("density" if re.search(r"г\s*/\s*м", part) else "composition", part)
            else:
                add(kind, value)

    return {"values": values, "lines": lines}


def plain_text(value) -> str:
    raw = text_of(value)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</p\s*>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html_mod.unescape(raw)
    raw = re.sub(r"[ \t\u00a0]+", " ", raw)
    return "\n".join(line.strip() for line in raw.split("\n") if line.strip())


def clip(text: str, limit: int = 175) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    cut = cut.rstrip(" ,;:.")
    if not cut.endswith((".", "!", "?", "…")):
        cut += "."
    return cut


def escape(value: str) -> str:
    return html_mod.escape(text_of(value), quote=False)


def strip_gender(name: str) -> str:
    match = GENDER_TAIL.match(name.strip())
    # Пол оставляем в H1, если без него остаётся одно слово: «Худи женское» →
    # «Худи» теряет смысл (ср. «Футболка «Летучка» женская» → «Футболка «Летучка»»).
    if match and len(match.group("base").split()) >= 2:
        return match.group("base").strip()
    return name.strip()


def stable_ids(slug: str) -> dict:
    """Стабильные числовые id блоков Tilda (один и тот же slug — те же id)."""
    digest = int(hashlib.sha1(slug.encode("utf-8")).hexdigest()[:10], 16)
    base = 8100000000 + (digest % 90000000)
    return {
        "page": str(72000000 + digest % 9000000),
        "gallery": str(base),
        "product": str(base + 1),
        "faq": str(base + 2),
        "faq_content": str(base + 3),
    }


def content_hash(product: dict) -> str:
    payload = {"product": product, "version": VERSION}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def grid_cells_bounds(text: str, grid_start: int) -> tuple[int, int]:
    """Границы ячеек сетки галереи: (начало ячеек, позиция закрывающего </div>).

    Меняем только ячейки. Если срезать регион до маркера <!--/gallery -->, теряется
    закрывающий </div> обёртки .t989__gallery-wrapper, и браузер вкладывает
    все последующие записи (карточку, FAQ) внутрь записи галереи.
    """
    inner_start = grid_start + len(GRID_START)
    depth = 1
    pos = inner_start
    while True:
        next_open = text.find("<div", pos)
        next_close = text.find("</div>", pos)
        if next_close < 0:
            raise PublishError("сетка галереи t989 не закрыта")
        if 0 <= next_open < next_close:
            depth += 1
            pos = next_open + 4
            continue
        depth -= 1
        if depth == 0:
            return inner_start, next_close
        pos = next_close + 6


def marker_of(text: str) -> dict:
    """Разбирает маркер <!-- jnn:publish slug=... hash=... --> из начала файла."""
    match = re.search(re.escape(MARKER_PREFIX) + r"([^>]*)-->", text or "")
    if not match:
        return {}
    out = {}
    for part in match.group(1).split():
        if "=" in part:
            key, _, value = part.partition("=")
            out[key.strip()] = value.strip()
    return out


# ---------------------------------------------------------------------------
# сборка страницы
# ---------------------------------------------------------------------------

def similar_items(product: dict, products: list[dict], limit: int = 2) -> list[dict]:
    current = slug_of(product)
    peers = [p for p in products
             if slug_of(p) and slug_of(p) != current and bool(p.get("show_in_catalog"))]
    peers.sort(key=lambda p: (p.get("sort") if isinstance(p.get("sort"), int) else 999, slug_of(p)))
    out = []
    for peer in peers[:limit]:
        fabric = parse_specs(peer)["values"]["fabric"]
        note = fabric.lower() if fabric else "модель из каталога"
        if price_of(peer):
            note += f", от {price_of(peer)} сом"
        out.append({"href": f"/{slug_of(peer)}.html", "text": text_of(peer.get("name")), "note": note})
    out.append({"href": "/uslugi-stm", "text": "Услуги СТМ",
                "note": "полный цикл: от лекала до упаковки под вашим брендом"})
    out.append({"href": "/conditions", "text": "Условия сотрудничества",
                "note": "подробно об оплате, доставке, возвратах"})
    return out


def build_values(product: dict, products: list[dict]) -> dict:
    slug = slug_of(product)
    if not slug:
        raise PublishError("у товара пустой slug — Directus не сможет отдать страницу")
    name = text_of(product.get("name")).strip() or slug
    h1 = strip_gender(name)
    sku = sku_of(product)
    price = price_of(product)
    specs = parse_specs(product)
    values = specs["values"]
    photos = photos_of(product)
    if not photos:
        raise PublishError(f"[{slug}] нет фото: заполните галерею (gallery) или image в Directus")

    lead = plain_text(product.get("description")).split("\n")
    if len(lead) == 1 and len(lead[0]) > 120:
        lead = [x.strip() for x in re.split(r"(?<=[.!?])\s+", lead[0]) if x.strip()]
    lead = [line for line in lead if line][:2]

    bits = [x for x in (values["fabric"], values["composition"], values["density"]) if x]
    if values["sizes"]:
        bits.append("размеры " + values["sizes"])
    tail = "Готовые модели со склада от 50 шт, пошив под заказ (СТМ) от 500 шт."
    meta = f"{name} оптом от производителя JNN Factory в Бишкеке"
    if bits:
        meta += ": " + ", ".join(bits)
    meta += ". " + tail

    micro_bits = [x for x in (values["fabric"], values["composition"], values["density"]) if x]
    micro = f"{name}"
    if micro_bits:
        micro += " из " + ", ".join(micro_bits)
    if values["sizes"]:
        micro += f", размеры {values['sizes']}"
    micro += ", минимальный заказ от 50 шт готовые или от 500 шт СТМ."

    sizes_line = (values["sizes"] + " в наличии.") if values["sizes"] else \
        "Размерный ряд уточняйте у менеджера."
    faq = [{"q": q, "a": a.format(sizes_line=sizes_line)} for q, a in FAQ_TEMPLATE]

    return {
        "slug": slug,
        "name": name,
        "h1": h1,
        "sku": sku,
        "price": price,
        "title": f"{name} оптом | Пошив в Бишкеке | JNN Factory",
        "desc_meta": clip(meta, 175).replace("'", "&#39;"),
        "og_title": name,
        "og_desc": clip(plain_text(product.get("description")) or meta, 200).replace("'", "&#39;"),
        "og_image": photos[0],
        "micro_name": name.replace("'", "&#39;"),
        "micro_desc": clip(micro, 300).replace("'", "&#39;"),
        "ld_desc": clip(plain_text(product.get("description")) or micro, 300),
        "spec_name": name,
        "spec_lines": specs["lines"],
        "lead": lead,
        "sizes": values["sizes"],
        "faq_title": f"{h1}: частые вопросы и детали заказа",
        "faq": faq,
        "similar": similar_items(product, products),
        "photos": photos,
        "ids": stable_ids(slug),
    }


# Микроразметку предложения держим валидной: в шаблоне это вложенный
# <div itemprop="offers" itemscope itemtype="Offer"> с <meta itemprop="price">,
# а не JSON-строка в content (такой content поисковики не разбирают).
TEMPLATE_OFFER_PRICE = '<meta itemprop="price" content="280"/>'
TEMPLATE_OFFER_URL = f'<meta itemprop="url" content="{SITE}/{TEMPLATE_SLUG}.html"/>'

# Маркеры вокруг JSON-LD товара: сами комментарии не меняются, поэтому вставка
# идемпотентна (повторный прогон даёт тот же результат даже для страницы-эталона).
LD_START = "<!-- jnn:product-ld:start -->"
LD_END = "<!-- jnn:product-ld:end -->"


def product_ld_html(values: dict) -> str:
    """JSON-LD @type Product — машинный дубль карточки для поисковиков и ИИ.

    Данные берём из тех же значений, что и вёрстку (Directus — источник истины),
    поэтому JSON-LD, микроразметка и видимая цена всегда совпадают.
    """
    photos = [p if p.startswith(("http://", "https://", "//")) else SITE + p
              for p in values["photos"]]
    offers = {
        "@type": "Offer",
        "url": f"{SITE}/{values['slug']}.html",
        "priceCurrency": "KGS",
        "availability": "https://schema.org/InStock",
        "itemCondition": "https://schema.org/NewCondition",
        "seller": {"@id": SITE + "/#organization"},
    }
    if values["price"]:
        offers["price"] = values["price"]
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": values["name"],
        "sku": values["sku"],
        "image": photos,
        "description": values["ld_desc"],
        "brand": {"@type": "Brand", "name": "JNN Factory"},
        "offers": offers,
    }
    return ("\n<script type=\"application/ld+json\">\n"
            + json.dumps(data, ensure_ascii=False, indent=2) + "\n</script>\n")


def replace_between(text: str, start: str, end: str, block: str, label: str) -> str:
    """Меняет всё между маркерами (сами маркеры остаются) — идемпотентная замена."""
    first = text.find(start)
    last = text.find(end, first + len(start)) if first >= 0 else -1
    if first < 0 or last < 0:
        raise PublishError(f"[{label}] не найдены маркеры {start!r} / {end!r}")
    return text[:first + len(start)] + block + text[last:]


def specs_html(values: dict) -> str:
    out = " " + escape(values["spec_name"]) + "<br/>| Артикул: " + (escape(values["sku"]) or "-") + "<br/>"
    for line in values["lead"]:
        out += "<strong>" + escape(line) + "</strong><br/>"
    for kind, value in values["spec_lines"]:
        if kind == "fabric":
            out += '<ul><li data-list="bullet">Ткань: ' + escape(value) + "</li></ul>"
        elif kind == "other":
            out += "• " + escape(value) + "<br/>"
        else:
            out += "• " + SPEC_LABELS.get(kind, kind) + ": " + escape(value) + "<br/>"
    out += "• " + CANON_MIN_ORDER
    return out


def faq_html(values: dict) -> str:
    out = " <h4>Часто задаваемые вопросы</h4> "
    for item in values["faq"]:
        out += "<p><strong>" + escape(item["q"]) + "</strong> " + escape(item["a"]) + "</p> "
    out += "<h4>Похожие модели</h4> <ul> "
    for item in values["similar"]:
        out += ('<li><a href="' + item["href"] + '">' + escape(item["text"]) + "</a> - " +
                escape(item["note"]) + "</li> ")
    out += ('</ul> <p style="margin-top:20px;"><strong>Нужен прайс или образец?</strong> '
            "Напишите в Telegram - ответим за 15 минут.</p> ")
    return out


def swap(text: str, find: str, repl: str, label: str) -> str:
    count = text.count(find)
    if count != 1:
        raise PublishError(f"[{label}] подстрока найдена {count} раз(а), ожидалась 1: {find[:90]}")
    return text.replace(find, repl, 1)


def swap_inner(text: str, anchor: str, inner: str, label: str) -> str:
    start = text.find(anchor)
    if start < 0:
        raise PublishError(f"[{label}] якорь не найден: {anchor[:90]}")
    begin = start + len(anchor)
    end = text.find("</div>", begin)
    if end < 0:
        raise PublishError(f"[{label}] не найден закрывающий </div>")
    return text[:begin] + inner + text[end:]


def render(template: str, values: dict, product: dict, products: list[dict]) -> str:
    out = template
    slug = values["slug"]
    draft = not bool(product.get("show_in_catalog"))
    link = f"{SITE}/{slug}.html"

    out = swap(out, '<title>Футболка "Летучка" оптом | Пошив в Бишкеке | JNN Factory</title>',
               "<title>" + values["title"] + "</title>", slug + ":title")
    out = swap(out,
               '<meta content=\'Производим женские футболки "Летучка" оптом. Стильный свободный крой, '
               'ткань "пенье компакт". Идеально для повседневного стиля и маркетплейсов.\' name="description"/>',
               "<meta content='" + values["desc_meta"] + "' name=\"description\"/>", slug + ":description")
    out = swap(out, f'<meta content="{SITE}/{TEMPLATE_SLUG}.html" property="og:url"/>',
               f'<meta content="{link}" property="og:url"/>', slug + ":og:url")
    out = swap(out, '<meta content="Футболка Летучка" property="og:title"/>',
               '<meta content="' + values["og_title"].replace('"', "&quot;") + '" property="og:title"/>',
               slug + ":og:title")
    out = swap(out, '<meta content="" property="og:description"/>',
               '<meta content="' + values["og_desc"] + '" property="og:description"/>', slug + ":og:description")
    out = swap(out,
               '<meta content="/assets/tildcdn/tild3231-6330-4135-b965-323533366339/504x/260A1229.jpg" '
               'property="og:image"/>',
               '<meta content="' + SITE + values["og_image"] + '" property="og:image"/>', slug + ":og:image")
    out = swap(out, f'<link href="{SITE}/{TEMPLATE_SLUG}.html" rel="canonical"/>',
               f'<link href="{link}" rel="canonical"/>', slug + ":canonical")
    out = swap(out, '<meta content="index, follow" name="robots"/>',
               '<meta content="' + ("noindex, follow" if draft else "index, follow") + '" name="robots"/>',
               slug + ":robots")
    out = swap(out, f'data-tilda-page-alias="{TEMPLATE_SLUG}" data-tilda-page-id="72600819"',
               f'data-tilda-page-alias="{slug}" data-tilda-page-id="{values["ids"]["page"]}"', slug + ":alias")

    out = swap(out, 'data-record-type="989" id="rec1172546201"',
               'data-record-type="989" id="rec' + values["ids"]["gallery"] + '"', slug + ":gallery-id")
    out = swap(out, "t989_init('1172546201')", "t989_init('" + values["ids"]["gallery"] + "')",
               slug + ":gallery-init")
    start = out.find(GRID_START)
    if start < 0:
        raise PublishError(f"[{slug}] не найдена сетка галереи t989")
    inner_start, inner_end = grid_cells_bounds(out, start)
    cells = ""
    for index, photo in enumerate(values["photos"]):
        alt = (f"{values['h1']} оптом от производителя JNN Factory в Бишкеке" if index == 0
               else f"{values['h1']} - фото {index + 1}")
        cells += ('<div style="padding:4px;"><img src="' + photo + '" loading="lazy" '
                  'style="width:100%;height:auto;border-radius:6px;display:block;" alt="' +
                  escape(alt) + '"></div>')
    out = out[:inner_start] + cells + out[inner_end:]

    out = swap(out, 'data-record-type="180" id="rec1172548121"',
               'data-record-type="180" id="rec' + values["ids"]["product"] + '"', slug + ":product-id")
    out = swap(out, '<meta itemprop="name" content="Футболка Летучка женская"/>',
               '<meta itemprop="name" content="' + values["micro_name"] + '"/>', slug + ":micro-name")
    out = swap(out,
               '<meta itemprop="description" content="Женская футболка Летучка из кулирной глади пенье компакт '
               '170 г/м², свободный крой, размер one-size (42-46), цвета черный и белый, минимальный заказ '
               'от 50 шт готовые или от 500 шт СТМ."/>',
               '<meta itemprop="description" content="' + values["micro_desc"] + '"/>', slug + ":micro-desc")
    out = swap(out, '<meta itemprop="sku" content="JNN-W-TS-001"/>',
               '<meta itemprop="sku" content="' + values["sku"] + '"/>', slug + ":sku")
    out = swap(out, TEMPLATE_OFFER_PRICE,
               '<meta itemprop="price" content="' + values["price"] + '"/>', slug + ":offer-price")
    out = swap(out, TEMPLATE_OFFER_URL,
               f'<meta itemprop="url" content="{link}"/>', slug + ":offer-url")
    out = swap(out, '<h1 class="t165__title t-heading t-heading_md" field="title">Футболка «Летучка»</h1>',
               '<h1 class="t165__title t-heading t-heading_md" field="title">' + escape(values["h1"]) + '</h1>',
               slug + ":h1")
    out = swap_inner(out, '</h1> <div class="t165__text t-text t-text_sm" field="text">',
                     specs_html(values), slug + ":specs")

    out = swap(out, 'data-record-type="60" id="rec_faq_letuchka"',
               'data-record-type="60" id="rec' + values["ids"]["faq"] + '"', slug + ":faq-id")
    out = swap(out, '<h3 class="t050__title t-title t-title_xxl" field="title">Всё о футболке «Летучка» - '
                    'FAQ и детали</h3>',
               '<h3 class="t050__title t-title t-title_xxl" field="title">' + escape(values["faq_title"]) + '</h3>',
               slug + ":faq-title")
    out = swap(out, 'data-record-type="165" id="rec_faq_content"',
               'data-record-type="165" id="rec' + values["ids"]["faq_content"] + '"', slug + ":faq-content-id")
    out = swap_inner(out, 'textwrapper"> <div class="t165__text t-text t-text_sm" field="text">',
                     faq_html(values), slug + ":faq-text")

    out = replace_between(out, LD_START, LD_END, product_ld_html(values), slug + ":product-ld")

    marker = (f"{MARKER_PREFIX} slug={slug} hash={content_hash(product)} generated={today()} "
              f"v={VERSION} -->")
    # Маркер ставим в самое начало файла: голова Tilda-страницы ~15 КБ, и читать
    # её целиком ради проверки «наша ли страница» не нужно.
    if out.count("<!DOCTYPE html>") == 1:
        out = out.replace("<!DOCTYPE html>", "<!DOCTYPE html>" + marker, 1)
    else:
        out = swap(out, "</head>", marker + "</head>", slug + ":marker")

    check_page(out, values, template)
    return out


def check_page(out: str, values: dict, template: str) -> None:
    slug = values["slug"]
    spans = []
    for match in re.finditer(r'<script type="application/ld\+json">', out):
        end = out.find("</script>", match.start())
        if end < 0:
            raise PublishError(f"[{slug}] блок JSON-LD не закрыт: нет </script>")
        spans.append((match.start(), end))
    for match in re.finditer("[—–]", out):
        if any(start <= match.start() < end for start, end in spans):
            continue
        raise PublishError(f"[{slug}] длинное тире вне JSON-LD: "
                           + repr(out[max(0, match.start() - 60):match.start() + 40]))
    # JSON-LD товара между маркерами обязан быть валидным и полным
    if LD_START not in out or LD_END not in out:
        raise PublishError(f"[{slug}] нет маркеров JSON-LD товара")
    block = out.split(LD_START, 1)[1].split(LD_END, 1)[0]
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', block, re.S)
    if not match:
        raise PublishError(f"[{slug}] в блоке JSON-LD нет <script type=application/ld+json>")
    try:
        data = json.loads(match.group(1))
    except ValueError as exc:
        raise PublishError(f"[{slug}] JSON-LD товара не парсится: {exc}")
    if data.get("@type") != "Product":
        raise PublishError(f"[{slug}] JSON-LD товара: @type != Product")
    for field in ("name", "sku", "image", "description", "offers"):
        if not data.get(field):
            raise PublishError(f"[{slug}] JSON-LD товара: пустое поле {field}")
    # не должно остаться ничего от эталона (фразы эталона с данными товара не совпадают;
    # исключение — если публикуем сам эталон, тогда его h1 законен)
    leftovers = [
        ('Футболка "Летучка" оптом | Пошив в Бишкеке', "остался title эталона"),
        ('Производим женские футболки "Летучка"', "осталось meta description эталона"),
        ('content="Футболка Летучка женская"', "осталось microdata name эталона"),
        ("Женская футболка Летучка из кулирной глади", "осталось microdata description эталона"),
        ("Всё о футболке «Летучка» - FAQ и детали", "остался заголовок FAQ эталона"),
        ("t989_init('1172546201')", "остался init галереи эталона"),
        ("/assets/letuchka_", "остались фото эталона"),
    ]
    if values["h1"] != TEMPLATE_H1:
        leftovers.append(("Футболка «Летучка»</h1>", "остался h1 эталона"))
    if values["slug"] != TEMPLATE_SLUG:
        leftovers.append((f'data-tilda-page-alias="{TEMPLATE_SLUG}"', "остался alias эталона"))
        leftovers.append((f'{SITE}/{TEMPLATE_SLUG}"', "осталась ссылка на слаг эталона"))
    for needle, label in leftovers:
        if needle in out:
            raise PublishError(f"[{slug}] {label}")
    # обязательный минимум готовой страницы
    for needle, label in ((WHATSAPP, "не найдена ссылка WhatsApp"),
                          (CANON_MIN_ORDER, "не найден канон минимального заказа"),
                          (MARKER_PREFIX, "не записан маркер публикации"),
                          (values["sku"], "не найден артикул"),
                          (values["h1"], "не найден h1"),
                          (values["photos"][0], "не найдено главное фото")):
        if needle and needle not in out:
            raise PublishError(f"[{slug}] {label}")
    if len(out) < len(template) * 0.9:
        raise PublishError(f"[{slug}] файл подозрительно короткий: {len(out)} < {len(template)}")


# ---------------------------------------------------------------------------
# sitemap.xml и llms
# ---------------------------------------------------------------------------

def today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def sitemap_upsert(root: str, slug: str, image_path: str, lastmod: str | None = None) -> str:
    path = os.path.join(root, "sitemap.xml")
    if not os.path.exists(path):
        raise PublishError(f"не найден {path}")
    text = read_text(path)
    loc = f"{SITE}/{slug}.html"
    block = ["  <url>", f"    <loc>{loc}</loc>", f"    <lastmod>{lastmod or today()}</lastmod>",
             "    <changefreq>monthly</changefreq>", f"    <priority>{PAGE_PRIORITY}</priority>"]
    if image_path:
        image_url = image_path if image_path.startswith("http") else SITE + image_path
        block += ["    <image:image>", f"      <image:loc>{image_url}</image:loc>", "    </image:image>"]
    block += ["  </url>"]
    pattern = re.compile(r"[ \t]*<url>\s*<loc>" + re.escape(loc) + r"</loc>.*?</url>\s*\n?", re.S)
    match = pattern.search(text)
    position = match.start() if match else None
    text = pattern.sub("", text)
    block_text = "\n".join(block) + "\n"
    if position is not None:
        text = text[:position] + block_text + text[position:]
    else:
        index = text.rfind("</urlset>")
        if index < 0:
            raise PublishError("в sitemap.xml нет закрывающего </urlset>")
        text = text[:index] + block_text + text[index:]
    write_text(path, text)
    return "updated" if match else "added"


def sitemap_remove(root: str, slug: str) -> bool:
    path = os.path.join(root, "sitemap.xml")
    if not os.path.exists(path):
        return False
    text = read_text(path)
    loc = f"{SITE}/{slug}.html"
    pattern = re.compile(r"[ \t]*<url>\s*<loc>" + re.escape(loc) + r"</loc>.*?</url>\s*\n?", re.S)
    if not pattern.search(text):
        return False
    write_text(path, pattern.sub("", text))
    return True


def catalog_line(values: dict, product: dict) -> str:
    spec = parse_specs(product)
    fabric = spec["values"]["fabric"]
    bits = []
    if fabric:
        bits.append(fabric[:1].lower() + fabric[1:])
    if spec["values"]["composition"]:
        bits.append(spec["values"]["composition"].replace(", ", " / "))
    if spec["values"]["density"]:
        bits.append(spec["values"]["density"])
    if price_of(product):
        bits.append(f"от {price_of(product)} сом")
    title = values["h1"] or values["name"]
    return (f"- [{title}]({SITE}/{values['slug']}.html): " + ", ".join(bits)) if bits else \
        f"- [{title}]({SITE}/{values['slug']}.html)"


def table_row(values: dict, product: dict, number: int) -> str:
    spec = parse_specs(product)["values"]
    fabric = spec["fabric"]
    if fabric:
        fabric = fabric[:1].lower() + fabric[1:]
    fabric_composition = ", ".join(x for x in (fabric, spec["composition"].replace(", ", " / ")) if x)
    sizes = spec["sizes"].replace(" - ", " – ")
    title = values["h1"] or values["name"]
    return (f"| {number} | [{title}]({SITE}/{values['slug']}.html) | {values['sku'] or '-'} | "
            f"{fabric_composition or '-'} | {spec['density'] or '-'} | {sizes or '-'} | "
            f"{('от ' + values['price'] + ' сом') if values['price'] else '-'} |")


def section_bounds(text: str, heading: str) -> tuple[int, int] | None:
    """Границы раздела markdown: от заголовка до следующего '## '."""
    start = text.find(heading)
    if start < 0:
        return None
    body = start + len(heading)
    nxt = text.find("\n## ", body)
    return (body, nxt if nxt >= 0 else len(text))


def section_count(text: str, heading: str, prefix: str) -> int:
    """Сколько строк-элементов каталога в разделе (для счётчика в заголовке)."""
    bounds = section_bounds(text, heading)
    if not bounds:
        return 0
    body, end = bounds
    return sum(1 for line in text[body:end].split("\n")
               if line.startswith(prefix) and f"{SITE}/" in line)


def llms_catalog_upsert(root: str, values: dict, product: dict, refresh: bool = False) -> str:
    path = os.path.join(root, "llms.txt")
    if not os.path.exists(path):
        raise PublishError(f"не найден {path}")
    heading = "## Каталог готовых моделей"
    text = read_text(path)
    loc = f"({SITE}/{values['slug']}.html)"
    lines = text.split("\n")
    old_index = None
    for index, line in enumerate(lines):
        if loc in line:
            old_index = index
            break
    line = catalog_line(values, product)
    if old_index is not None:
        # Строку обновляем, только если данные в Directus изменились: иначе цены
        # и состав в llms.txt навсегда отстали бы от товара (sync без refresh).
        if lines[old_index].strip() == line.strip() and not refresh:
            return "actual (строка совпадает с Directus)"
        del lines[old_index]
    if old_index is None:
        bounds = section_bounds("\n".join(lines), heading)
        if not bounds:
            raise PublishError("в llms.txt нет раздела «Каталог готовых моделей»")
        body, end = bounds
        chunk = "\n".join(lines)[body:end].split("\n")
        insert_at = len(chunk)
        for index in range(len(chunk) - 1, -1, -1):
            if chunk[index].startswith("- ["):
                insert_at = index + 1
                break
        chunk.insert(insert_at, line)
        joined = "\n".join(lines)
        lines = (joined[:body] + "\n".join(chunk) + joined[end:]).split("\n")
    else:
        lines.insert(old_index, line)
    text = "\n".join(lines)
    count = section_count(text, heading, "- [")
    text = re.sub(r"\b(\d+)( базовых модел)", lambda m: f"{count}{m.group(2)}", text)
    write_text(path, text)
    return line


def llms_catalog_remove(root: str, slug: str) -> bool:
    path = os.path.join(root, "llms.txt")
    if not os.path.exists(path):
        return False
    text = read_text(path)
    loc = f"({SITE}/{slug}.html)"
    keep = [line for line in text.split("\n") if loc not in line]
    if len(keep) == len(text.split("\n")):
        return False
    text = "\n".join(keep)
    count = section_count(text, "## Каталог готовых моделей", "- [")
    text = re.sub(r"\b(\d+)( базовых модел)", lambda m: f"{count}{m.group(2)}", text)
    write_text(path, text)
    return True


def llms_full_upsert(root: str, values: dict, product: dict, refresh: bool = False) -> str:
    path = os.path.join(root, "llms-full.txt")
    if not os.path.exists(path):
        raise PublishError(f"не найден {path}")
    heading = "Каталог готовых моделей"
    text = read_text(path)
    loc = f"({SITE}/{values['slug']}.html)"
    lines = text.split("\n")
    old_index = None
    number = 0
    for index, line in enumerate(lines):
        if line.startswith("| ") and loc in line:
            old_index = index
            try:
                number = int(line.split("|")[1].strip())
            except ValueError:
                number = 0
            break
    if not number:
        probe = [text for index, text in enumerate(lines) if index != old_index]
        number = section_count("\n".join(probe), heading, "| ") + 1
    row = table_row(values, product, number)
    if old_index is not None:
        # Как и в llms.txt: обновляем строку, если она разошлась с Directus.
        if lines[old_index].strip() == row.strip() and not refresh:
            return "actual (строка совпадает с Directus)"
        del lines[old_index]
    if old_index is not None:
        lines.insert(old_index, row)
    else:
        joined = "\n".join(lines)
        bounds = section_bounds(joined, heading)
        if not bounds:
            raise PublishError("в llms-full.txt нет раздела «Каталог готовых моделей»")
        body, end = bounds
        chunk = joined[body:end].split("\n")
        insert_at = len(chunk)
        for index in range(len(chunk) - 1, -1, -1):
            if chunk[index].startswith("| ") and f"{SITE}/" in chunk[index]:
                insert_at = index + 1
                break
        chunk.insert(insert_at, row)
        lines = (joined[:body] + "\n".join(chunk) + joined[end:]).split("\n")
    text = "\n".join(lines)
    count = section_count(text, heading, "| ")
    text = re.sub(r"\b(\d+)( базовых позици)", lambda m: f"{count}{m.group(2)}", text)
    write_text(path, text)
    return row


def llms_full_remove(root: str, slug: str) -> bool:
    path = os.path.join(root, "llms-full.txt")
    if not os.path.exists(path):
        return False
    text = read_text(path)
    loc = f"({SITE}/{slug}.html)"
    keep = [line for line in text.split("\n") if loc not in line]
    if len(keep) == len(text.split("\n")):
        return False
    text = "\n".join(keep)
    count = section_count(text, "Каталог готовых моделей", "| ")
    text = re.sub(r"\b(\d+)( базовых позици)", lambda m: f"{count}{m.group(2)}", text)
    write_text(path, text)
    return True


# ---------------------------------------------------------------------------
# логирование
# ---------------------------------------------------------------------------

def log_event(record: dict) -> None:
    try:
        path = os.path.join(SITE_ROOT, LOG_NAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 — лог не должен ломать публикацию
        pass


def read_log(limit: int = 20) -> list[dict]:
    path = os.path.join(SITE_ROOT, LOG_NAME)
    if not os.path.exists(path):
        return []
    lines = read_text(path).strip().split("\n")
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# публикация
# ---------------------------------------------------------------------------

def publish_product(product: dict, products: list[dict], force: bool = False, dry: bool = False,
                    root: str | None = None, refresh_llms: bool = False) -> dict:
    root = root or SITE_ROOT
    slug = slug_of(product)
    draft = not bool(product.get("show_in_catalog"))
    path = os.path.join(root, slug + ".html")
    values = build_values(product, products)
    template = read_text(os.path.join(SITE_ROOT, TEMPLATE_DIR, TEMPLATE_NAME))
    html = render(template, values, product, products)

    exists = os.path.exists(path)
    old_marker = marker_of(read_head(path)) if exists else {}
    if exists and not old_marker and not force:
        return {"ok": False, "skipped": True, "slug": slug, "page": path,
                "reason": "страница создана вручную (нет маркера jnn:publish) — нужен force=true"}

    report = {
        "ok": True,
        "slug": slug,
        "page": path,
        "url": f"{SITE}/{slug}.html",
        "action": "update" if exists else "create",
        "draft": draft,
        "photos": len(values["photos"]),
        "bytes": len(html),
        "dry": dry,
        "page_bytes": None,
        "sitemap": "skip",
        "llms": "skip",
        "llms_full": "skip",
        "warnings": [],
    }
    if values["price"] and not re.fullmatch(r"\d+", values["price"]):
        report["warnings"].append("цена не число — microdata без цены")
    if not values["sizes"]:
        report["warnings"].append("нет размеров (поле sizes / bullets)")
    if not values["spec_lines"]:
        report["warnings"].append("нет характеристик (поле bullets) — блок specs будет коротким")
    if text_of(product.get("min_order")).strip() and text_of(product.get("min_order")).strip() != CANON_MIN_ORDER:
        report["warnings"].append("min_order в Directus отличается от канона — на странице использован канон")

    if dry:
        return report

    before = os.path.getsize(path) if exists else 0
    write_text(path, html)
    report["page_bytes"] = f"{before} -> {len(html)}"

    if not draft:
        report["sitemap"] = sitemap_upsert(root, slug, values["og_image"])
        report["llms"] = "line: " + llms_catalog_upsert(root, values, product, refresh=refresh_llms)
        report["llms_full"] = "row: " + llms_full_upsert(root, values, product, refresh=refresh_llms)
    log_event({**report, "ts": datetime.datetime.now().isoformat(timespec="seconds"), "hash": old_marker.get("hash")})
    return report


def publish_slug(slug: str, force: bool = False, dry: bool = False, root: str | None = None,
                 refresh_llms: bool = False) -> dict:
    products = fetch_products()
    product = next((p for p in products if slug_of(p) == slug), None)
    if not product:
        raise PublishError(f"товар со slug «{slug}» не найден в Directus")
    return publish_product(product, products, force=force, dry=dry, root=root, refresh_llms=refresh_llms)


def sync(dry: bool = False, force: bool = False, root: str | None = None,
         refresh_llms: bool = False) -> dict:
    """Догоняет Directus: создаёт страницы для новых товаров, обновляет изменённые."""
    root = root or SITE_ROOT
    products = fetch_products()
    results = []
    for product in products:
        slug = slug_of(product)
        if not slug or not bool(product.get("show_in_catalog")):
            continue
        path = os.path.join(root, slug + ".html")
        if os.path.exists(path):
            marker = marker_of(read_head(path))
            # force нужен, чтобы забрать страницу под управление публикатора:
            # без него ручные страницы не трогаем (иначе перезапишем чужую вёрстку).
            if not marker and not force:
                results.append({"slug": slug, "action": "skip",
                                "reason": "страница создана вручную (нет маркера jnn:publish) — нужен force"})
                continue
            if marker.get("hash") == content_hash(product) and not force:
                results.append({"slug": slug, "action": "skip", "reason": "актуальна"})
                continue
        try:
            results.append(publish_product(product, products, force=force, dry=dry, root=root,
                                           refresh_llms=refresh_llms))
        except PublishError as exc:
            results.append({"slug": slug, "ok": False, "error": str(exc)})

    known = {slug_of(p) for p in products}
    orphans = []
    for name in sorted(os.listdir(root)):
        if not name.endswith(".html"):
            continue
        slug = name[:-5]
        if slug in known or slug in ("index", "404"):
            continue
        try:
            marker = marker_of(read_head(os.path.join(root, name)))
        except OSError:
            continue
        if marker.get("slug") == slug:
            orphans.append(slug)
    return {"ok": True, "dry": dry, "published": results, "orphans": orphans}


def unpublish(slug: str, force: bool = False, dry: bool = False, root: str | None = None) -> dict:
    """Снимает страницу товара: файл + запись в sitemap + строки в llms."""
    root = root or SITE_ROOT
    path = os.path.join(root, slug + ".html")
    if not os.path.exists(path):
        raise PublishError(f"страница {path} не найдена")
    marker = marker_of(read_head(path))
    if not marker and not force:
        raise PublishError(f"[{slug}] страница создана вручную — удаление только с force=true")
    if dry:
        return {"ok": True, "dry": True, "slug": slug, "page": path, "action": "unpublish"}
    os.remove(path)
    removed = {"page": True, "sitemap": sitemap_remove(root, slug),
               "llms": llms_catalog_remove(root, slug), "llms_full": llms_full_remove(root, slug)}
    log_event({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "action": "unpublish",
               "slug": slug, "removed": removed})
    return {"ok": True, "slug": slug, "action": "unpublish", "removed": removed}


def all_missing(force: bool = False, dry: bool = False, root: str | None = None,
                refresh_llms: bool = False) -> dict:
    root = root or SITE_ROOT
    products = fetch_products()
    results = []
    for product in products:
        slug = slug_of(product)
        if not slug or os.path.exists(os.path.join(root, slug + ".html")):
            continue
        try:
            results.append(publish_product(product, products, force=force, dry=dry, root=root,
                                           refresh_llms=refresh_llms))
        except PublishError as exc:
            results.append({"slug": slug, "ok": False, "error": str(exc)})
    return {"ok": True, "dry": dry, "published": results}


def status(root: str | None = None) -> dict:
    root = root or SITE_ROOT
    products = fetch_products()
    sitemap = read_text(os.path.join(root, "sitemap.xml")) if os.path.exists(os.path.join(root, "sitemap.xml")) else ""
    llms = read_text(os.path.join(root, "llms.txt")) if os.path.exists(os.path.join(root, "llms.txt")) else ""
    items = []
    for product in products:
        slug = slug_of(product)
        path = os.path.join(root, slug + ".html")
        page = os.path.exists(path)
        marker = marker_of(read_head(path)) if page else {}
        items.append({
            "slug": slug,
            "name": text_of(product.get("name")),
            "in_catalog": bool(product.get("show_in_catalog")),
            "page": page,
            "page_ours": bool(marker),
            "actual": bool(marker) and marker.get("hash") == content_hash(product),
            "sitemap": f"{SITE}/{slug}.html" in sitemap if sitemap else None,
            "llms": f"{SITE}/{slug}.html" in llms if llms else None,
        })
    return {"ok": True, "site_root": root, "directus": DIRECTUS, "count": len(items),
            "with_page": sum(1 for x in items if x["page"]),
            "without_page": sum(1 for x in items if not x["page"]),
            "ours": sum(1 for x in items if x["page_ours"]),
            "items": items}


def _ids_to_slugs(raw) -> list[str]:
    ids = []
    for chunk in re.findall(r"\d+", text_of(raw)):
        ids.append(int(chunk))
    if not ids:
        return []
    products = fetch_products()
    return [slug_of(p) for p in products if p.get("id") in ids and slug_of(p)]


def api_publish(payload: dict) -> dict:
    """Обработчик POST /gallery-api/publish — и для вебхука Directus, и для рук."""
    payload = payload or {}
    dry = bool(payload.get("dry"))
    force = bool(payload.get("force"))
    refresh = bool(payload.get("refresh_llms") or payload.get("refresh"))
    if payload.get("slug"):
        return publish_slug(text_of(payload["slug"]).strip(), force=force, dry=dry, refresh_llms=refresh)
    if payload.get("slugs"):
        slugs = payload["slugs"]
        if isinstance(slugs, str):
            slugs = [x for x in re.split(r"[,\s]+", slugs) if x]
        return {"ok": True,
                "published": [publish_slug(s, force=force, dry=dry, refresh_llms=refresh) for s in slugs]}
    if any(field in payload for field in ("keys", "key", "ids")):
        # Directus: для items.update приходит keys (массив), для items.create — key;
        # отсутствующее поле подставляется строкой "undefined" — просто игнорируем.
        raw = " ".join(text_of(payload.get(field)) for field in ("keys", "key", "ids"))
        slugs = _ids_to_slugs(raw)
        if slugs:
            return {"ok": True,
                    "published": [publish_slug(s, force=force, dry=dry, refresh_llms=refresh) for s in slugs]}
        return sync(dry=dry, force=force, refresh_llms=refresh)
    if payload.get("unpublish"):
        return unpublish(text_of(payload["unpublish"]).strip(), force=force, dry=dry)
    if payload.get("all_missing"):
        return all_missing(force=force, dry=dry, refresh_llms=refresh)
    if payload.get("sync") or payload.get("action") or payload.get("event"):
        return sync(dry=dry, force=force, refresh_llms=refresh)
    return {"ok": False, "error": "нужен slug / slugs / keys / all_missing / sync"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Публикация товара Directus -> сайт (страница + sitemap + llms)")
    parser.add_argument("--slug", help="слаг товара в Directus")
    parser.add_argument("--sync", action="store_true", help="создать отсутствующие и обновить изменённые страницы")
    parser.add_argument("--all-missing", action="store_true", help="опубликовать только товары без страницы")
    parser.add_argument("--unpublish", metavar="SLUG", help="снять страницу (файл + sitemap + llms)")
    parser.add_argument("--force", action="store_true", help="перезаписать ручную страницу")
    parser.add_argument("--refresh-llms", action="store_true",
                        help="перезаписать существующие строки в llms.txt / llms-full.txt данными из Directus")
    parser.add_argument("--dry", action="store_true", help="показать план, ничего не писать")
    parser.add_argument("--out", metavar="DIR", help="писать в другой каталог (для проверки)")
    parser.add_argument("--list", action="store_true", help="состояние товаров: страница, sitemap, llms")
    parser.add_argument("--log", type=int, nargs="?", const=20, metavar="N", help="последние записи журнала")
    args = parser.parse_args(argv)

    root = args.out or SITE_ROOT
    try:
        if args.out and os.path.abspath(args.out) != os.path.abspath(SITE_ROOT):
            os.makedirs(args.out, exist_ok=True)
            for name in ("sitemap.xml", "llms.txt", "llms-full.txt"):
                src, dst = os.path.join(SITE_ROOT, name), os.path.join(args.out, name)
                if os.path.exists(src) and not os.path.exists(dst):
                    write_text(dst, read_text(src))

        if args.list:
            result = status(root)
        elif args.log is not None:
            result = {"ok": True, "log": read_log(args.log)}
        elif args.unpublish:
            result = unpublish(args.unpublish, force=args.force, dry=args.dry, root=root)
        elif args.slug:
            result = publish_slug(args.slug, force=args.force, dry=args.dry, root=root,
                                  refresh_llms=args.refresh_llms)
        elif args.all_missing:
            result = all_missing(force=args.force, dry=args.dry, root=root, refresh_llms=args.refresh_llms)
        elif args.sync:
            result = sync(dry=args.dry, force=args.force, root=root, refresh_llms=args.refresh_llms)
        else:
            parser.print_help()
            return 2
    except PublishError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=1))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
