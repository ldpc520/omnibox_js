# -*- coding: utf-8 -*-
# @name 4K影视
# @author OmniBox-Spider
# @description 影视站：https://www.4kvms.org，支持首页、分类筛选、搜索、详情与播放页解析
# @version 1.1.0
# @dependencies 无第三方依赖（纯标准库正则解析，服务端渲染 HTML 可直接抓取）
#
# 站点结构备忘（2026-09 实测）：
#   首页       /                          区块式推荐，无分页
#   分类筛选   /filter?classify=1&page=1  真正的分类/筛选/分页入口（classify 1电影 2电视剧 3动漫 4综艺）
#   搜索       /search?q=关键词           单页返回，最多 20 条，无分页
#   详情       /play/{slug}               服务端渲染，含选集列表（data-line / data-episode / dataid）
#
# 关于播放直链（2026-09 逆向实测，已实现免登录解析）：
#   接口       /video/play?p={dataid}&v={slug}&q={quality}&s={sign}&t={时间戳ms}&k={令牌}
#   签名       sign = HMAC-SHA256(key=slug, msg="{dataid}:{t}:{slug}") 的 hex 前 32 位
#              （WASM build_play_url 逆向结果；q 与 k 不参与签名）
#   令牌       k = base64( userlink 逐字节 XOR "nbmovie2024secretkey" 循环 )
#              userlink 由播放页 HTML 内嵌（未登录访客也有，x-data 内 userlink:'...'）
#   清晰度     q=1080 返回的 quality_urls 里 4K 为 VIP 锁定，1080p 免费可播；
#              4K 仅客户端支持，720 及以下需 VIP，因此固定请求 1080 并取未锁定直链
#   直链       返回 m3u8（oss.douyinbit.com），请求头带 UA/Referer 即可播放

import base64
import hashlib
import hmac
import html
import json
import os
import re
import time
from urllib.parse import parse_qs, quote, urljoin, urlparse

from spider_runner import OmniBox, run


BASE_URL = os.environ.get("KVMS4K_HOST", "https://www.4kvms.org").rstrip("/")
UA = os.environ.get(
    "KVMS4K_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"{BASE_URL}/",
}

# 分类：对应 /filter?classify=
CLASS_LIST = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "动漫"},
    {"type_id": "4", "type_name": "综艺"},
]
CLASS_IDS = {item["type_id"] for item in CLASS_LIST}

# 以下取值均来自 /filter 页面的实际链接参数
AREA_OPTIONS = [
    ("5", "美国"), ("6", "法国"), ("7", "中国"), ("11", "日本"), ("12", "韩国"),
    ("14", "中国香港"), ("16", "俄罗斯"), ("17", "波兰"), ("18", "德国"), ("19", "意大利"),
    ("21", "中国台湾"), ("22", "澳大利亚"), ("24", "西班牙"), ("30", "英国"), ("32", "加拿大"),
    ("33", "泰国"), ("34", "印度"), ("41", "丹麦"), ("52", "中国大陆"), ("65", "马来西亚"),
    ("74", "菲律宾"), ("78", "其他"), ("79", "瑞典"), ("80", "挪威"), ("81", "阿根廷"),
    ("82", "冰岛"), ("83", "保加利亚"), ("84", "爱尔兰"), ("86", "墨西哥"), ("87", "比利时"),
    ("88", "瑞士"), ("89", "克罗地亚"), ("91", "马耳他"), ("92", "匈牙利"), ("93", "西德"),
    ("94", "新西兰"), ("95", "哥伦比亚"), ("96", "巴西"), ("97", "印度尼西亚"),
]

TYPE_OPTIONS = [
    ("1", "剧情"), ("2", "悬疑"), ("3", "恐怖"), ("4", "惊悚"), ("5", "喜剧"),
    ("6", "爱情"), ("9", "犯罪"), ("10", "动作"), ("11", "动画"), ("12", "奇幻"),
    ("13", "音乐"), ("14", "科幻"), ("15", "历史"), ("16", "战争"), ("18", "冒险"),
    ("19", "家庭"), ("20", "纪录"), ("23", "西部"), ("24", "电视电影"), ("26", "真人秀"),
    ("27", "古装"), ("28", "传记"), ("30", "运动"), ("31", "武侠"), ("32", "歌舞"),
    ("33", "纪录片"), ("34", "灾难"), ("35", "短片"),
]

YEAR_OPTIONS = [
    ("78", "2027"), ("1", "2026"), ("3", "2025"), ("4", "2024"), ("56", "2023"),
    ("13", "2022"), ("2", "2021"), ("6", "2020"), ("8", "2019"), ("9", "2018"),
    ("12", "2017"), ("11", "2016"), ("14", "2015"), ("15", "2014"), ("22", "2013"),
    ("10", "2012"), ("17", "2011"), ("25", "2010"), ("20", "2009"), ("23", "2008"),
    ("30", "2007"), ("31", "2006"), ("7", "2005"), ("24", "2004"), ("28", "2003"),
    ("19", "2002"), ("29", "2001"), ("43", "2000"), ("45", "1999"), ("33", "1998"),
    ("34", "1997"), ("37", "1996"), ("21", "1995"), ("27", "1994"), ("26", "1993"),
    ("35", "1992"), ("18", "1991"), ("42", "1990"), ("44", "1989"), ("60", "1988"),
    ("73", "1987"), ("32", "1986"), ("40", "1985"), ("63", "1984"), ("59", "1983"),
    ("36", "1982"), ("5", "1981"), ("39", "1980"), ("61", "1979"), ("66", "1978"),
    ("48", "1977"), ("38", "1976"), ("57", "1975"), ("62", "1974"), ("53", "1973"),
    ("54", "1972"), ("51", "1971"), ("41", "1969"), ("77", "1968"), ("76", "1966"),
    ("58", "1965"), ("46", "1963"), ("65", "1962"), ("71", "1961"), ("75", "1960"),
    ("16", "1959"), ("67", "1958"), ("50", "1957"), ("49", "1956"), ("47", "1955"),
    ("68", "1954"), ("72", "1952"), ("70", "1949"), ("64", "1948"),
]

TAG_OPTIONS = [("1", "4k"), ("36", "院线"), ("37", "TC")]

SORT_OPTIONS = [
    ("update_time", "最新上映"),
    ("hits", "最受欢迎"),
    ("score", "评分最高"),
]

PAGE_SIZE = 24  # /filter 每页固定 24 条


def make_options(pairs):
    return [{"name": "全部", "value": ""}] + [
        {"name": name, "value": value} for value, name in pairs
    ]


FILTERS = {
    category_id: [
        {"key": "types", "name": "类型", "value": make_options(TYPE_OPTIONS)},
        {"key": "areas", "name": "地区", "value": make_options(AREA_OPTIONS)},
        {"key": "years", "name": "年份", "value": make_options(YEAR_OPTIONS)},
        {"key": "tags", "name": "标签", "value": make_options(TAG_OPTIONS)},
        {"key": "sort_by", "name": "排序", "value": make_options(SORT_OPTIONS)},
    ]
    for category_id in CLASS_IDS
}

# 列表卡片：首页/分类页以 data-vod-id 为锚点，搜索页仅有链接，回退用 href 锚点
CARD_SPLIT_RE = re.compile(r'data-vod-id="([^"]+)"')
HREF_SPLIT_RE = re.compile(r'href="/play/([A-Za-z0-9]+)"')
IMG_RE = re.compile(r'data-src="([^"]+)"')
H3_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
SCORE_RE = re.compile(r"text-yellow-400[^>]*>(?:.*?</svg>)?\s*([\d.]+)", re.S)
# 备注按优先级排列：更新状态 > 完结状态 > 画质标签
REMARK_PATTERNS = [
    re.compile(r"更新至\s*\d+\s*集"),
    re.compile(r"全\s*\d+\s*集"),
    re.compile(r"\b4k\b", re.I),
    re.compile(r"院线"),
    re.compile(r"\bTC\b"),
    re.compile(r"\bHD\b"),
    re.compile(r"\bBD\b"),
]
YEAR_BADGE_RE = re.compile(r"top-2 left-2[^>]*>\s*(\d{4})\s*<", re.S)
# 仅匹配「标签内纯年份文本」，避免误抓图片 URL 里的 app=2001 之类数字
YEAR_FALLBACK_RE = re.compile(r">\s*(19\d{2}|20\d{2})\s*<")

# 详情页字段：label / value 相邻网格
FIELD_RE = re.compile(
    r"<div[^>]*>\s*(导演|编剧|主演|类型|地区|语言|上映|又名|片长|集数)\s*</div>\s*"
    r"<div[^>]*>(.*?)</div>",
    re.S,
)
# 选集：<a href="/play/xxx" ... data-line="1" data-episode="2" dataid="1552" ...>
# 注意：标签内 Alpine 表达式含 "=>"（如 () => {...}），不能简单用 [^>]* 截断，
# 因此先整体捕获 <a ...>...</a>，再从其中提取属性，文本取最后一个 ">" 之后的内容。
EPISODE_RE = re.compile(
    r'<a\s(?P<attrs>[\s\S]*?data-episode="(?P<episode>\d+)"[\s\S]*?)>'
    r"(?P<text>[\s\S]*?)</a>",
    re.S,
)
UPDATE_RE = re.compile(r"(更新至[^<，,]{0,20})")


def clean_text(value):
    text = str(value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def normalize_page(value):
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def normalize_filters(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def abs_url(value):
    raw = clean_text(value)
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = f"{urlparse(BASE_URL).scheme}:{raw}"
    return urljoin(f"{BASE_URL}/", raw)


def is_site_url(value):
    expected = urlparse(BASE_URL)
    candidate = urlparse(value)
    return (
        candidate.scheme in {"http", "https"}
        and candidate.scheme == expected.scheme
        and candidate.netloc.lower() == expected.netloc.lower()
    )


def is_direct_media(url):
    return bool(re.search(r"\.(?:m3u8|mp4|mkv|flv|mpd)(?:[?#]|$)", url or "", re.I))


PLAY_SECRET = b"nbmovie2024secretkey"


def encode_k(userlink):
    """k = base64( userlink 逐字节 XOR 循环密钥 )，与站点 WASM 行为一致。"""
    raw = str(userlink or "").encode("utf-8")
    if not raw:
        return "0"
    cipher = bytes(c ^ PLAY_SECRET[i % len(PLAY_SECRET)] for i, c in enumerate(raw))
    return base64.b64encode(cipher).decode("ascii")


def build_play_api_url(dataid, slug, quality="1080", userlink="", timestamp=None):
    """构造带签名的播放接口地址（HMAC-SHA256，前 32 位 hex）。"""
    ts = str(timestamp if timestamp is not None else int(time.time() * 1000))
    sign = hmac.new(
        slug.encode("utf-8"),
        "{0}:{1}:{2}".format(dataid, ts, slug).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    query = "p={0}&v={1}&q={2}&s={3}&t={4}&k={5}".format(
        quote(str(dataid), safe=""),
        quote(str(slug), safe=""),
        quote(str(quality), safe=""),
        sign,
        quote(ts, safe=""),
        quote(encode_k(userlink), safe=""),
    )
    return "{0}/video/play?{1}".format(BASE_URL, query)


def pick_free_stream(quality_urls):
    """优先取未锁定的免费直链（1080p），VIP 专享的跳过。"""
    for item in quality_urls or []:
        url = str(item.get("url") or "")
        if not item.get("locked") and url.startswith("http"):
            return url
    return ""


async def log(level, message):
    try:
        await OmniBox.log(level, f"[4K影视] {message}")
    except Exception:
        pass


async def request_text(url, referer=None):
    headers = dict(HEADERS)
    headers["Referer"] = referer or f"{BASE_URL}/"
    response = await OmniBox.request(
        url,
        {
            "method": "GET",
            "headers": headers,
            "timeout": 30000,
        },
    )
    status = int(response.get("statusCode") or 0)
    body = response.get("body", "")
    text = body.decode("utf-8", "ignore") if isinstance(body, (bytes, bytearray)) else str(body or "")
    if not 200 <= status < 300:
        raise RuntimeError(f"HTTP {status or 'unknown'} @ {url}")
    return text


def iter_card_blocks(text):
    """产出 (vod_id, body) 元组：优先 data-vod-id 卡片，回退到 /play/ 链接锚点。"""
    parts = CARD_SPLIT_RE.split(text)
    if len(parts) > 2:
        for index in range(1, len(parts) - 1, 2):
            yield parts[index], parts[index + 1]
        return
    chunks = HREF_SPLIT_RE.split(text)
    for index in range(1, len(chunks) - 1, 2):
        yield chunks[index], chunks[index + 1]


def parse_cards(text, limit=None):
    """解析首页 / 分类页 / 搜索结果页的影片卡片。"""
    videos = []
    seen = set()
    for vod_id, body in iter_card_blocks(text):
        if vod_id in seen:
            continue
        seen.add(vod_id)

        title = clean_text(H3_RE.search(body).group(1)) if H3_RE.search(body) else ""
        if not title:
            alt = re.search(r'alt="([^"]+)"', body)
            title = clean_text(alt.group(1)) if alt else ""
        if not title:
            continue

        poster = ""
        img = IMG_RE.search(body)
        if img:
            poster = abs_url(img.group(1))
        if not poster or "placeholder" in poster:
            og = re.search(r'data-src="([^"]+)"', body)
            poster = abs_url(og.group(1)) if og else ""

        year_match = YEAR_BADGE_RE.search(body)
        year = year_match.group(1) if year_match else ""
        if not year:
            fallback = YEAR_FALLBACK_RE.search(body)
            year = fallback.group(1) if fallback else ""

        score_match = SCORE_RE.search(body)
        score = score_match.group(1) if score_match else ""

        remarks = ""
        for pattern in REMARK_PATTERNS:
            found = pattern.search(body)
            if found:
                remarks = clean_text(found.group(0))
                break
        if not remarks and score:
            remarks = f"{score}分"

        videos.append(
            {
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": poster,
                "vod_remarks": remarks,
                "vod_year": year,
                "vod_score": score,
            }
        )
        if limit and len(videos) >= limit:
            break
    return videos


def parse_page_info(text, default_page=1):
    """从 /filter 结果页解析总页数与总数。"""
    match = re.search(r"共\s*(\d+)\s*页[^0-9]*(\d+)?", text)
    if match:
        pagecount = max(1, int(match.group(1)))
        total = int(match.group(2)) if match.group(2) else 0
        return pagecount, total
    pages = [int(p) for p in re.findall(r"[?&]page=(\d+)", text)]
    return (max(pages) if pages else default_page), 0


def parse_labeled_fields(text):
    """解析详情页的「标签-值」网格。"""
    fields = {}
    for match in FIELD_RE.finditer(text):
        label = clean_text(match.group(1))
        value = clean_text(match.group(2))
        value = re.sub(r"\s*/\s*", " / ", value)
        if label and value and label not in fields:
            fields[label] = value
    return fields


def parse_episodes(text):
    """解析选集，按 data-line 分组为多个播放源。"""
    grouped = {}
    order = []
    for match in EPISODE_RE.finditer(text):
        try:
            number = int(match.group("episode"))
        except (TypeError, ValueError):
            continue
        chunk = f"{match.group('attrs')}>{match.group('text')}"
        slug = re.search(r'href="/play/([A-Za-z0-9]+)"', chunk)
        if not slug:
            continue
        line_match = re.search(r'data-line="([^"]*)"', chunk)
        dataid_match = re.search(r'dataid="([^"]*)"', chunk)
        line = clean_text(line_match.group(1)) if line_match else "1"
        dataid = clean_text(dataid_match.group(1)) if dataid_match else ""

        # 取标签之间的可见文本节点，过滤掉可能残留的属性/脚本片段
        fragments = re.findall(r">\s*([^<>]+?)\s*<", match.group("text"))
        name = ""
        for fragment in reversed(fragments):
            candidate = clean_text(fragment)
            if not candidate or len(candidate) > 20:
                continue
            if any(marker in candidate for marker in ("=", "{", "}", '"', "'")):
                continue
            name = candidate
            break
        if not name:
            name = f"第{number}集"
        elif name.isdigit():
            name = f"第{name}集"

        if line not in grouped:
            grouped[line] = {}
            order.append(line)
        grouped[line][number] = {
            "name": name,
            # playId 携带 dataid，play 阶段据此请求签名直链接口
            "playId": "{0}/play/{1}{2}".format(
                BASE_URL,
                slug.group(1),
                "?dataid={0}".format(dataid) if dataid else "",
            ),
            "dataid": dataid,
            "line": line,
        }

    sources = []
    for line in order or sorted(grouped):
        episodes = grouped.get(line) or {}
        if not episodes:
            continue
        sources.append(
            {
                "name": f"线路{line}",
                "episodes": [episodes[n] for n in sorted(episodes)],
            }
        )
    return sources


def extract_description(text):
    match = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', text)
    if not match:
        match = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', text)
    content = clean_text(match.group(1)) if match else ""
    content = re.sub(r"^搜索\s*.*?的结果$", "", content)
    return re.sub(r"^(?:简介|剧情介绍)\s*[：:]?\s*", "", content).strip()


def build_legacy_play_fields(sources):
    from_names = []
    url_groups = []
    for source in sources:
        from_names.append(clean_text(source.get("name")) or "默认")
        episodes = source.get("episodes") or []
        url_groups.append(
            "#".join(
                f"{clean_text(ep.get('name')) or '播放'}${clean_text(ep.get('playId'))}"
                for ep in episodes
                if clean_text(ep.get("playId"))
            )
        )
    return "|".join(from_names), "|".join(url_groups)


def extract_video_id(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    raw = clean_text(value)
    match = re.search(r"/play/([A-Za-z0-9]+)", raw)
    if match:
        return match.group(1)
    match = re.search(r"^([A-Za-z0-9]{6,20})$", raw)
    return match.group(1) if match else raw


def parse_detail_html(text, vod_id):
    title = ""
    match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', text)
    if match:
        title = re.sub(r"\s*-\s*第?\d+集\s*$", "", clean_text(match.group(1))).strip()
    if not title:
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
        title = clean_text(h1.group(1)) if h1 else ""

    poster = ""
    og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]*)"', text)
    if og:
        poster = abs_url(og.group(1))

    fields = parse_labeled_fields(text)
    sources = parse_episodes(text)
    play_from, play_url = build_legacy_play_fields(sources)

    remarks = ""
    update = UPDATE_RE.search(text)
    if update:
        remarks = clean_text(update.group(1))
    if not remarks:
        tag = re.search(r"bg-dark-700 text-gray-300 text-xs rounded\">\s*([^<]+?)\s*<", text)
        remarks = clean_text(tag.group(1)) if tag else ""

    year_value = fields.get("上映", "")
    year_match = re.search(r"(19\d{2}|20\d{2})", year_value)

    return {
        "vod_id": str(vod_id),
        "vod_name": title,
        "vod_pic": poster,
        "type_name": fields.get("类型", ""),
        "vod_year": year_match.group(1) if year_match else year_value,
        "vod_area": fields.get("地区", ""),
        "vod_lang": fields.get("语言", ""),
        "vod_remarks": remarks,
        "vod_actor": fields.get("主演", ""),
        "vod_director": fields.get("导演", ""),
        "vod_writer": fields.get("编剧", ""),
        "vod_content": extract_description(text),
        "vod_play_sources": sources,
        "vod_play_from": play_from,
        "vod_play_url": play_url,
    }


async def home(params=None, context=None):
    try:
        text = await request_text(f"{BASE_URL}/")
        videos = parse_cards(text, limit=60)
        await log("info", f"home count={len(videos)}")
        return {"class": CLASS_LIST, "filters": FILTERS, "list": videos}
    except Exception as error:
        await log("error", f"home 失败: {error}")
        return {"class": CLASS_LIST, "filters": FILTERS, "list": []}


def build_filter_url(category_id, page, filters):
    params = {"classify": str(category_id)}
    if page > 1:
        params["page"] = str(page)
    for key in ("types", "areas", "years", "tags"):
        value = clean_text(filters.get(key))
        if value:
            params[key] = value
    sort_by = clean_text(filters.get("sort_by"))
    if sort_by:
        params["sort_by"] = sort_by
        params["order"] = "desc"
    # 兼容 Python < 3.12：f-string 表达式内不能复用外层引号，改用普通字符串拼接
    pairs = [
        quote(str(k), safe="") + "=" + quote(str(v), safe="")
        for k, v in params.items()
    ]
    return f"{BASE_URL}/filter?" + "&".join(pairs)


async def category(params, context=None):
    page = normalize_page((params or {}).get("page"))
    try:
        category_id = clean_text(
            (params or {}).get("categoryId") or (params or {}).get("type_id") or "1"
        )
        if category_id not in CLASS_IDS:
            raise ValueError(f"无效分类: {category_id}")
        filters = normalize_filters(
            (params or {}).get("filters")
            or (params or {}).get("extend")
            or (params or {}).get("ext")
        )
        url = build_filter_url(category_id, page, filters)
        text = await request_text(url)
        videos = parse_cards(text)
        pagecount, total = parse_page_info(text, default_page=page)
        limit = len(videos) or PAGE_SIZE
        await log("info", f"category id={category_id} page={page}/{pagecount} count={len(videos)}")
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": limit,
            "total": total or pagecount * limit,
            "list": videos,
        }
    except Exception as error:
        await log("error", f"category 失败: {error}")
        return {"page": page, "pagecount": 0, "limit": 0, "total": 0, "list": []}


async def detail(params, context=None):
    try:
        vod_id = extract_video_id(
            (params or {}).get("videoId")
            or (params or {}).get("vod_id")
            or (params or {}).get("id")
        )
        if not vod_id:
            return {"list": []}
        text = await request_text(f"{BASE_URL}/play/{vod_id}")
        item = parse_detail_html(text, vod_id)
        if not item or not item.get("vod_name"):
            return {"list": []}
        await log(
            "info",
            f"detail id={vod_id} sources={len(item.get('vod_play_sources') or [])}",
        )
        return {"list": [item]}
    except Exception as error:
        await log("error", f"detail 失败: {error}")
        return {"list": []}


async def search(params, context=None):
    page = normalize_page((params or {}).get("page"))
    try:
        keyword = clean_text(
            (params or {}).get("keyword")
            or (params or {}).get("wd")
            or (params or {}).get("q")
            or (params or {}).get("key")
        )
        if not keyword:
            return {"page": page, "pagecount": 0, "limit": 0, "total": 0, "list": []}
        url = f"{BASE_URL}/search?q={quote(keyword, safe='')}"
        text = await request_text(url)
        blocked = any(
            marker in text for marker in ("验证码", "人机验证", "安全验证", "just_a_test")
        )
        videos = [] if blocked else parse_cards(text)
        limit = len(videos) or PAGE_SIZE
        await log("info", f"search keyword={keyword} count={len(videos)}")
        return {
            "page": 1,
            "pagecount": 1 if videos else 0,
            "limit": limit,
            "total": len(videos),
            "list": videos,
        }
    except Exception as error:
        await log("error", f"search 失败: {error}")
        return {"page": page, "pagecount": 0, "limit": 0, "total": 0, "list": []}


def build_play_result(url, name, parse, header=None):
    headers = header or {}
    return {
        "parse": int(parse),
        "playUrl": "",
        "url": url,
        "urls": [{"name": name or "播放", "url": url}] if url else [],
        "header": headers,
        "headers": headers,
    }


async def play(params, context=None):
    play_id = clean_text(
        (params or {}).get("playId")
        or (params or {}).get("id")
        or (params or {}).get("url")
    )
    flag = clean_text((params or {}).get("flag")) or "播放"
    headers = {"User-Agent": UA, "Referer": f"{BASE_URL}/"}
    play_page = ""
    try:
        if not play_id:
            return build_play_result("", flag, 1, headers)

        # 已是直链则直接播放
        if is_direct_media(play_id):
            return build_play_result(play_id, flag, 0, headers)

        # playId 既可能是完整播放页地址，也可能只是 /play/ 后的 slug
        if "/play/" in play_id:
            play_page = abs_url(play_id)
        else:
            play_page = abs_url(f"/play/{play_id}")
        if not is_site_url(play_page):
            raise ValueError("播放页不属于 4K影视站点")

        # 解析 slug 与选集 dataid（detail 阶段已写入 ?dataid=）
        slug_match = re.search(r"/play/([A-Za-z0-9]+)", urlparse(play_page).path)
        if not slug_match:
            raise ValueError("无法从播放地址解析 slug")
        slug = slug_match.group(1)
        query = parse_qs(urlparse(play_page).query)
        dataid = clean_text((query.get("dataid") or [""])[0])

        # 拉播放页：取访客 userlink，并在未指定 dataid 时回退到第一个选集
        page_text = await request_text(play_page)
        userlink = ""
        userlink_match = re.search(r"userlink:'([^']*)'", page_text)
        if userlink_match:
            userlink = clean_text(userlink_match.group(1))
        if not dataid:
            dataid_match = re.search(r'dataid="(\d+)"', page_text)
            dataid = dataid_match.group(1) if dataid_match else ""
        if not userlink or not dataid:
            raise ValueError("播放页缺少 userlink 或 dataid")

        # 请求签名直链接口，取免费 1080p 流
        api_url = build_play_api_url(dataid, slug, "1080", userlink)
        body = json.loads(await request_text(api_url, referer=play_page))
        stream = ""
        if int(body.get("code") or 0) == 200:
            stream = pick_free_stream((body.get("data") or {}).get("quality_urls"))
        if stream:
            await log("info", "play 直链解析成功: {0}".format(stream[:80]))
            return build_play_result(stream, flag, 0, headers)

        # 未取到直链则回退页面嗅探
        message = clean_text(body.get("message") or "未获取到免费播放地址")
        await log("info", "play 直链解析失败({0})，回退页面嗅探".format(message))
        return build_play_result(play_page, flag, 1, headers)
    except Exception as error:
        await log("error", f"play 失败: {error}")
        if play_page:
            return build_play_result(play_page, flag, 1, headers)
        return build_play_result("", flag, 1, headers)


if __name__ == "__main__":
    run(
        {
            "home": home,
            "category": category,
            "detail": detail,
            "search": search,
            "play": play,
        }
    )
