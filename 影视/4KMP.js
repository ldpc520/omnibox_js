// @name 4KMP
// @author 梦
// @description 4kmp.com 已迁移至 4k-av.com（多语言 WordPress 站点：/en/、/zh/、根路径=简体中文）。
//              支持首页、分类、搜索、详情与直链播放。纯正则解析，无第三方依赖（不依赖 cheerio）。
//              注意：详情页播放器为 JS 动态渲染，静态 HTML 无 <video>/<source>，play() 依赖嗅探兜底。
// @version 1.1.1
// @downloadURL https://gh-proxy.org/https://github.com/Silent1566/OmniBox-Spider/raw/refs/heads/main/影视/采集/4KMP.js

const OmniBox = require("omnibox_sdk");
const runner = require("spider_runner");

// 4kmp.com 现已别名/重定向到 4k-av.com；直接指向新域名，避免旧路径 404。
const BASE_URL = "https://4k-av.com";
const IMG_HOST = "https://www.4k-av.com";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15";
const REQUEST_TIMEOUT = Number(process.env.KMP_TIMEOUT || 20000);

const CLASS_LIST = [
  { type_id: "movie", type_name: "电影" },
  { type_id: "tv", type_name: "电视剧" },
];

const YEAR_VALUES = [
  { name: "全部", value: "" },
  { name: "2026", value: "2026" },
  { name: "2025", value: "2025" },
  { name: "2024", value: "2024" },
  { name: "2023", value: "2023" },
  { name: "2022", value: "2022" },
  { name: "2021", value: "2021" },
  { name: "2020", value: "2020" },
  { name: "2019", value: "2019" },
];

// 年份为可靠过滤（站点存在 /{year}/ 归档页）；标签路径未确认，保留 UI 但构建时不改变路径。
const TAG_VALUES = [
  { name: "全部", value: "" },
  { name: "动作", value: "动作" },
  { name: "剧情", value: "剧情" },
  { name: "喜剧", value: "喜剧" },
  { name: "科幻", value: "科幻" },
  { name: "悬疑", value: "悬疑" },
  { name: "惊悚", value: "惊悚" },
  { name: "恐怖", value: "恐怖" },
  { name: "战争", value: "战争" },
  { name: "犯罪", value: "犯罪" },
  { name: "动画", value: "动画" },
  { name: "纪录片", value: "纪录片" },
];

const FILTERS = {
  movie: [
    { key: "year", name: "年份", init: "", value: YEAR_VALUES },
    { key: "tag", name: "标签", init: "", value: TAG_VALUES },
  ],
  tv: [
    { key: "year", name: "年份", init: "", value: YEAR_VALUES },
    { key: "tag", name: "标签", init: "", value: TAG_VALUES },
  ],
};

module.exports = { home, category, detail, search, play };
runner.run(module.exports);

function getBodyText(res) {
  const body = res && typeof res === "object" && "body" in res ? res.body : res;
  if (Buffer.isBuffer(body)) return body.toString("utf8");
  if (body instanceof Uint8Array) return Buffer.from(body).toString("utf8");
  return String(body || "");
}

function cleanText(value) {
  return String(value || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&#183;/g, "·")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function getAttr(tagHtml, name) {
  const m = tagHtml.match(new RegExp(`\\s${name}\\s*=\\s*["']([^"']*)["']`, "i"));
  return m ? m[1] : "";
}

function getMeta(html, key) {
  const m1 = html.match(new RegExp(`<meta[^>]+(?:property|name)=["']${key}["'][^>]*?content=["']([^"']*)["']`, "i"));
  if (m1) return decodeEntities(m1[1]);
  const m2 = html.match(new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]*?(?:property|name)=["']${key}["']`, "i"));
  return m2 ? decodeEntities(m2[1]) : "";
}

function decodeEntities(value) {
  return String(value || "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&#183;/g, "·")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">");
}

function getTagText(html, tag, className) {
  let re;
  if (className) {
    re = new RegExp(`<${tag}\\b[^>]*class=["'][^"']*${className}[^"']*["'][^>]*>([\\s\\S]*?)<\\/${tag}>`, "i");
  } else {
    re = new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i");
  }
  const m = html.match(re);
  return m ? cleanText(m[1]) : "";
}

// 提取页面中所有 <a> 标签：href / title / 内部文本 / 内部图片 src+alt
function extractAnchors(html) {
  const anchors = [];
  const re = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
  let m;
  while ((m = re.exec(html || ""))) {
    const openTag = m[1];
    const inner = m[2];
    const href = getAttr(openTag, "href");
    if (!href) continue;
    const titleAttr = decodeEntities(getAttr(openTag, "title"));
    const imgSrc =
      (inner.match(/<img\b[^>]*\ssrc=["']([^"']+)["']/i) ||
        inner.match(/<img\b[^>]*\sdata-src=["']([^"']+)["']/i) ||
        inner.match(/<img\b[^>]*\sdata-original=["']([^"']+)["']/i) || [])[1] || "";
    const imgAlt = decodeEntities((inner.match(/<img\b[^>]*\salt=["']([^"']*)["']/i) || [])[1] || "");
    anchors.push({ href, titleAttr, imgSrc, imgAlt, text: cleanText(inner) });
  }
  return anchors;
}

function absUrl(url) {
  const value = String(url || "").trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("//")) return `https:${value}`;
  if (value.startsWith("/")) return `${BASE_URL}${value}`;
  return `${BASE_URL}/${value.replace(/^\.\//, "")}`;
}

// 从详情/卡片链接中提取 {type, id, slug}，用于构造海报地址。
// 例：https://4k-av.com/en/movie/005147-the-pig-the-snake-and-the-pigeon/  => movie / 005147-the-pig-the-snake-and-the-pigeon
function parseIdSlug(url) {
  const m = String(url || "").match(/\/(movie|tv)\/(\d+(?:-[^/?#]+)?)\/?/i);
  if (!m) return null;
  return { type: m[1].toLowerCase(), idSlug: m[2] };
}

function buildPosterUrl(url) {
  const info = parseIdSlug(url);
  if (!info) return "";
  return `${IMG_HOST}/${info.type}/${info.idSlug}/poster_nail.jpg`;
}

function buildHeaders(referer = `${BASE_URL}/`, extra = {}) {
  return {
    "User-Agent": UA,
    Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    Referer: referer || `${BASE_URL}/`,
    ...extra,
  };
}

function buildPlayHeaders(referer = `${BASE_URL}/`) {
  return {
    "User-Agent": UA,
    Referer: referer || `${BASE_URL}/`,
    Origin: BASE_URL,
  };
}

async function fetchText(url, options = {}) {
  const finalUrl = absUrl(url);
  await OmniBox.log("info", `[4KMP][request] ${finalUrl}`);
  const res = await OmniBox.request(finalUrl, {
    method: options.method || "GET",
    headers: buildHeaders(options.referer, options.headers || {}),
    body: options.body,
    timeout: options.timeout || REQUEST_TIMEOUT,
  });
  const statusCode = Number(res?.statusCode || 0);
  if (!res || statusCode !== 200) {
    throw new Error(`HTTP ${res?.statusCode || "unknown"} @ ${finalUrl}`);
  }
  return getBodyText(res);
}

function dedupeById(list) {
  const seen = new Set();
  return (list || []).filter((item) => {
    const key = item?.vod_id || item?.playId || item?.url;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function detectTypeId(href) {
  const value = String(href || "");
  if (/\/tv\//i.test(value)) return "tv";
  if (/\/movie\//i.test(value)) return "movie";
  return "";
}

// 容错列表解析：基于链接模式匹配 /movie/ 或 /tv/ 后跟数字编号的卡片，
// 不依赖具体容器 class（新站点容器类名未知）。
function parseVodList(html) {
  const anchors = extractAnchors(html);
  const list = [];
  for (const a of anchors) {
    if (!/\/(movie|tv)\/\d+(?:-[^/?#]+)?\/?$/i.test(a.href)) continue;
    const typeId = detectTypeId(a.href);
    if (!typeId) continue;

    const title = a.titleAttr || a.imgAlt || a.text;
    if (!title || /^(电影|电视剧|TV|Movies|Movie|TV series)$/i.test(title)) continue;
    if (title.length < 2) continue;

    const rawUrl = absUrl(a.href);
    const pic = absUrl(a.imgSrc) || buildPosterUrl(rawUrl);

    list.push({
      vod_id: rawUrl,
      vod_name: title,
      vod_pic: pic,
      vod_url: rawUrl,
      vod_remarks: "",
      vod_year: "",
      vod_subtitle: "",
      vod_content: "",
      type_id: typeId,
      type_name: "",
    });
  }
  return dedupeById(list);
}

function parsePageCount(html) {
  const textMatch = String(html || "").match(/页次\s*\d+\s*\/\s*(\d+)/);
  if (textMatch) {
    const count = Number(textMatch[1]);
    if (Number.isFinite(count) && count > 0) return count;
  }

  let maxPage = 1;
  let match;
  // WordPress 分页：/movie/page/2/
  const regex = /\/page\/(\d+)\//gi;
  while ((match = regex.exec(String(html || "")))) {
    const page = Number(match[1]);
    if (Number.isFinite(page) && page > maxPage) maxPage = page;
  }
  // 旧式：page-N.html（兜底）
  const regex2 = /page-(\d+)\.html/gi;
  while ((match = regex2.exec(String(html || "")))) {
    const page = Number(match[1]);
    if (Number.isFinite(page) && page > maxPage) maxPage = page;
  }
  return maxPage;
}

function normalizeExtend(params) {
  return params?.extend || params?.filters || {};
}

function buildCategoryBasePath(typeId, extend = {}) {
  const year = String(extend.year || "").trim();
  if (/^(19|20)\d{2}$/.test(year)) return `/${year}/`;
  const id = String(typeId || "movie").trim();
  if (id === "tv" || id === "movie") return `/${id}/`;
  return "/movie/";
}

function buildPagedPath(basePath, page) {
  if (!page || page <= 1) return basePath;
  const path = basePath.endsWith("/") ? basePath : `${basePath}/`;
  return `${path}page/${page}/`;
}

function buildPlayId(meta) {
  return JSON.stringify(meta || {});
}

function looksLikeMedia(url) {
  return /\.(m3u8|mp4|m4v|mov|flv)(\?|#|$)/i.test(String(url || ""));
}

// 解析播放源：<video><source>、<iframe>、以及文本中散落的 m3u8/mp4 直链
function parseMediaSources(html, pageUrl) {
  const list = [];

  const srcRe = /<source\b[^>]*\ssrc=["']([^"']+)["'][^>]*>/gi;
  let m;
  while ((m = srcRe.exec(html || ""))) {
    const src = m[1];
    if (!looksLikeMedia(src)) continue;
    const labelMatch = m[0].match(/\s(?:label|title)=["']([^"']*)["']/i);
    const quality = labelMatch ? cleanText(labelMatch[1]) : "";
    list.push({ name: quality || "直链", url: absUrl(src), header: buildPlayHeaders(pageUrl) });
  }

  const iframeRe = /<iframe\b[^>]*\ssrc=["']([^"']+)["']/gi;
  while ((m = iframeRe.exec(html || ""))) {
    const src = m[1];
    if (!looksLikeMedia(src)) continue;
    list.push({ name: "iframe", url: absUrl(src), header: buildPlayHeaders(pageUrl) });
  }

  const inlineRe = /https?:\/\/[^\s"'<>]+\.(?:m3u8|mp4|m4v|mov|flv)(?:\?[^\s"'<>]*)?/gi;
  let im;
  while ((im = inlineRe.exec(html || ""))) {
    list.push({ name: "直链", url: im[0], header: buildPlayHeaders(pageUrl) });
  }

  return dedupeById(list);
}

function extractDetailInfo(html, pageUrl) {
  const titleMatch = html.match(/<title>([\s\S]*?)<\/title>/i);
  const vodName =
    (titleMatch ? cleanText(titleMatch[1].split(" - ")[0]) : "") ||
    getTagText(html, "h1") ||
    getMeta(html, "og:title") ||
    cleanText((html.match(/<h1\b[^>]*\stitle=["']([^"']*)["']/i) || [])[1] || "");

  let vodPic = getMeta(html, "og:image");
  if (!vodPic) {
    const pm =
      html.match(/<img\b[^>]*class=["'][^"']*poster[^"']*["'][^>]*\ssrc=["']([^"']+)["']/i) ||
      html.match(/<img\b[^>]*\ssrc=["']([^"']+)["'][^>]*class=["'][^"']*poster[^"']*["']/i);
    if (pm) vodPic = pm[1];
  }
  vodPic = absUrl(vodPic) || buildPosterUrl(pageUrl);

  const vodContent =
    getMeta(html, "description") ||
    cleanText((html.match(/<div class=["'][^"']*entry-content[^"']*["'][^>]*>([\s\S]*?)<\/div>/i) || [,""])[1] || "");

  const plain = cleanText(html);
  const yearMatch = plain.match(/Year\s*[:：]?\s*(\d{4})/i) || plain.match(/\b(?:19|20)\d{2}\b/);
  const resMatch = plain.match(/Resolution\s*[:：]?\s*([0-9A-Za-z\s\/]+?)(?:Length|Year|$)/i);
  const vodYear = yearMatch ? yearMatch[1] : "";
  const vodRemarks = resMatch ? cleanText(resMatch[1]) : "";

  // 剧集列表：匹配 tv 详情下的分集链接（-s01e01 / -ep01 等后缀）
  const episodes = [];
  for (const a of extractAnchors(html)) {
    if (!/\/tv\/\d+(?:-[^/?#]+)?(?:-s\d+e\d+|-ep\d+)\/?$/i.test(a.href)) continue;
    const title = a.titleAttr || a.text || vodName;
    const episodePage = absUrl(a.href);
    episodes.push({
      name: title || vodName || "播放",
      playId: buildPlayId({ page: episodePage, title: title || vodName || "播放", vodName, pic: vodPic }),
    });
  }

  if (!episodes.length) {
    episodes.push({
      name: vodRemarks || "正片",
      playId: buildPlayId({ page: pageUrl, title: vodRemarks || "正片", vodName, pic: vodPic }),
    });
  }

  const playSources = [{ name: "4KMP", episodes: dedupeById(episodes) }];

  return {
    vod_id: pageUrl,
    vod_name: vodName,
    vod_pic: vodPic,
    vod_content: vodContent,
    vod_subtitle: "",
    vod_year: vodYear,
    vod_remarks: vodRemarks,
    type_id: detectTypeId(pageUrl),
    type_name: "",
    vod_play_sources: playSources,
  };
}

function normalizeKeyword(value) {
  return String(value || "")
    .replace(/[\s\-_—–·•:：,，.。!?！？'"“”‘’()（）\[\]【】{}]/g, "")
    .toLowerCase();
}

function scoreSearchResult(vodName, keyword) {
  const name = normalizeKeyword(vodName);
  const key = normalizeKeyword(keyword);
  if (!name || !key) return 0;
  if (name === key) return 1000 + key.length;
  if (name.startsWith(key)) return 800 + key.length;
  if (name.includes(key)) return 600 + key.length;
  if (key.includes(name) && name.length >= 2) return 400 + name.length;
  return 0;
}

function refineSearchResults(list, keyword) {
  const scored = (list || []).map((item, index) => ({
    item,
    index,
    score: scoreSearchResult(item.vod_name, keyword),
  }));
  const matched = scored
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map((entry) => entry.item);
  return matched.length ? matched : list;
}

function parseRawPlayId(raw) {
  const value = String(raw || "").trim();
  if (!value) return {};
  if (value.startsWith("{")) {
    try {
      return JSON.parse(value);
    } catch (_) {}
  }
  if (/^https?:\/\//i.test(value) || value.startsWith("/")) return { page: absUrl(value), title: "播放" };
  return { page: value, title: "播放" };
}

async function home(params, context) {
  try {
    const html = await fetchText(`${BASE_URL}/`);
    const list = parseVodList(html).slice(0, 36);
    await OmniBox.log("info", `[4KMP][home] list=${list.length}`);
    return {
      class: CLASS_LIST.map((item) => ({ ...item })),
      filters: FILTERS,
      list,
    };
  } catch (error) {
    await OmniBox.log("error", `[4KMP][home] ${error.message}`);
    return { class: CLASS_LIST.map((item) => ({ ...item })), filters: FILTERS, list: [] };
  }
}

async function category(params, context) {
  const page = Math.max(1, Number(params?.page || params?.pg || 1) || 1);
  try {
    const typeId = params?.type_id || params?.categoryId || params?.tid || "movie";
    const extend = normalizeExtend(params);
    const basePath = buildCategoryBasePath(typeId, extend);
    const firstHtml = await fetchText(basePath);
    const pageCount = parsePageCount(firstHtml);
    const html = page <= 1 ? firstHtml : await fetchText(buildPagedPath(basePath, page), { referer: absUrl(basePath) });
    const list = parseVodList(html);
    await OmniBox.log("info", `[4KMP][category] type=${typeId} page=${page} pageCount=${pageCount} list=${list.length}`);
    return {
      page,
      pagecount: Math.max(pageCount, page),
      total: Math.max(pageCount, page) * Math.max(list.length, 30),
      list,
    };
  } catch (error) {
    await OmniBox.log("error", `[4KMP][category] ${error.message}`);
    return { page, pagecount: page, total: 0, list: [] };
  }
}

async function detail(params, context) {
  try {
    const vodId = String(params?.vod_id || params?.videoId || params?.id || "").trim();
    if (!vodId) return { list: [] };
    const pageUrl = absUrl(vodId);
    const html = await fetchText(pageUrl);
    const info = extractDetailInfo(html, pageUrl);
    await OmniBox.log("info", `[4KMP][detail] ${info.vod_name} episodes=${info.vod_play_sources?.[0]?.episodes?.length || 0}`);
    return { list: [info] };
  } catch (error) {
    await OmniBox.log("error", `[4KMP][detail] ${error.message}`);
    return { list: [] };
  }
}

async function search(params, context) {
  const page = Math.max(1, Number(params?.page || params?.pg || 1) || 1);
  try {
    const keyword = String(params?.keyword || params?.key || params?.wd || "").trim();
    if (!keyword) return { page, pagecount: 0, total: 0, list: [] };
    // WordPress 搜索：/?s=关键词（语言路径可选，如 /en/?s=）
    const url = `${BASE_URL}/?s=${encodeURIComponent(keyword)}`;
    const html = await fetchText(url);
    const list = refineSearchResults(parseVodList(html), keyword);
    await OmniBox.log("info", `[4KMP][search] keyword=${keyword} list=${list.length}`);
    return {
      page,
      pagecount: 1,
      total: list.length,
      list,
    };
  } catch (error) {
    await OmniBox.log("error", `[4KMP][search] ${error.message}`);
    return { page, pagecount: 0, total: 0, list: [] };
  }
}

async function play(params, context) {
  try {
    const raw = String(params?.playId || params?.play_id || params?.id || "").trim();
    const meta = parseRawPlayId(raw);
    const pageUrl = meta.page ? absUrl(meta.page) : "";
    const direct = meta.direct ? absUrl(meta.direct) : "";
    const headers = buildPlayHeaders(pageUrl || `${BASE_URL}/`);

    if (direct && looksLikeMedia(direct)) {
      return {
        parse: 0,
        jx: 0,
        url: direct,
        urls: [{ name: meta.title || "直链", url: direct }],
        header: headers,
        headers,
      };
    }

    if (!pageUrl) {
      return { parse: 0, jx: 0, url: "", urls: [], header: {}, headers: {} };
    }

    const html = await fetchText(pageUrl, { referer: `${BASE_URL}/` });
    const mediaSources = parseMediaSources(html, pageUrl);
    const firstUrl = mediaSources[0]?.url || "";
    if (firstUrl) {
      const playHeaders = buildPlayHeaders(pageUrl);
      return {
        parse: 0,
        jx: 0,
        url: firstUrl,
        urls: mediaSources.map((item) => ({ name: item.name, url: item.url })),
        header: playHeaders,
        headers: playHeaders,
      };
    }

    // 播放器为 JS 动态渲染：静态 HTML 无直链，尝试嗅探兜底
    if (typeof OmniBox.sniffVideo === "function") {
      try {
        const sniffed = await OmniBox.sniffVideo(pageUrl, headers);
        const sniffUrl = sniffed?.url || sniffed?.playUrl || sniffed?.src || "";
        if (sniffUrl) {
          return {
            parse: 0,
            jx: 0,
            url: sniffUrl,
            urls: [{ name: meta.title || "嗅探线路", url: sniffUrl }],
            header: sniffed.header || sniffed.headers || headers,
            headers: sniffed.header || sniffed.headers || headers,
          };
        }
      } catch (error) {
        await OmniBox.log("warn", `[4KMP][play] sniffVideo failed: ${error.message}`);
      }
    }

    return {
      parse: 1,
      jx: 1,
      url: pageUrl,
      urls: [{ name: meta.title || "播放页", url: pageUrl }],
      header: headers,
      headers,
    };
  } catch (error) {
    await OmniBox.log("error", `[4KMP][play] ${error.message}`);
    return { parse: 0, jx: 0, url: "", urls: [], header: {}, headers: {} };
  }
}
