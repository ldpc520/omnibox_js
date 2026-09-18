# -*- coding: utf-8 -*-
# @name 金牌影院
# @version 1.0.4
# @downloadURL https://example.com/jinpai.omnibox.py
# @dependencies requests

import hashlib
import time
import json
import re
from urllib.parse import quote

from spider_runner import OmniBox, run

HOST = "https://www.jiabaide.cn"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
ERROR_URL = "https://sf1-cdn-tos.huoshanstatic.com/obj/media-fe/xgplayer_doc_video/mp4/xgplayer-demo-720p.mp4"
API_KEY = "cb808529bae6b6be45ecfab29a4889bc"


def _sign(data_str):
    """生成签名"""
    data_md5 = hashlib.md5(data_str.encode()).hexdigest()
    return hashlib.sha1(data_md5.encode()).hexdigest()


def _headers():
    return {
        "User-Agent": UA,
        "Referer": HOST,
    }


def _parse_vod(item):
    """解析视频项"""
    return {
        "vod_id": str(item.get("vodId", "")),
        "vod_name": item.get("vodName", ""),
        "vod_pic": item.get("vodPic", ""),
        "vod_remarks": item.get("vodVersion", "") if item.get("typeId1") == 1 else item.get("vodRemarks", ""),
    }


async def home(params, context):
    """首页"""
    await OmniBox.log("info", f"[home] from={context.get('from', 'web')}")
    
    classes = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "电视剧"},
        {"type_id": "3", "type_name": "综艺"},
        {"type_id": "4", "type_name": "动漫"},
        {"type_id": "5", "type_name": "短剧"},
    ]
    
    list_items = []
    try:
        # 从首页获取推荐数据
        r = await OmniBox.request(HOST, {"method": "GET", "headers": _headers()})
        if r.get("statusCode") == 200:
            html = r.get("body", "")
            # 解析首页JSON数据
            m = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});', html, re.S)
            if m:
                try:
                    nuxt_data = json.loads(m.group(1))
                    # 提取各类别推荐
                    for key in ['newestMoviePageData', 'newestTvPageData', 'newestVarietyPageData', 'newestCartoonPageData', 'newestShortTvPageData']:
                        page_data = nuxt_data.get('state', {}).get('default', {}).get(key, {})
                        for item in page_data.get('list', []):
                            list_items.append(_parse_vod(item))
                except:
                    pass
        
        # 获取热门搜索
        t = str(int(time.time() * 1000))
        sign_data = f"key={API_KEY}&t={t}"
        sign = _sign(sign_data)
        
        res = await OmniBox.request(f"{HOST}/api/mw-movie/anonymous/home/hotSearch", {
            "method": "GET",
            "headers": {**_headers(), "t": t, "sign": sign}
        })
        
        if res.get("statusCode") == 200:
            data = json.loads(res.get("body", "{}"))
            for item in data.get("data", []):
                list_items.append(_parse_vod(item))
                
    except Exception as e:
        await OmniBox.log("error", f"[home] 失败: {e}")
    
    # 去重
    seen = set()
    unique_items = []
    for item in list_items:
        if item["vod_id"] not in seen:
            seen.add(item["vod_id"])
            unique_items.append(item)
    
    return {"class": classes, "list": unique_items[:20]}


async def category(params, context):
    """分类列表（兼容搜索）"""
    # rebo.py 模式：首页点击视频时，前端传 keyword 到 category，必须按搜索处理
    keyword = (params.get("keyword") or params.get("wd") or "").strip()
    if keyword:
        await OmniBox.log("info", f"[category] 收到 keyword={keyword}，按搜索处理")
        return await search({"keyword": keyword, "page": params.get("page") or 1}, context)

    cid = params.get("categoryId", params.get("tid") or "1")
    page = int(params.get("page") or 1)
    ext = params.get("filters") or {}
    
    # 原脚本参数解析
    _type = ext.get("type", "") if ext.get("type") else ""
    __class = ext.get("class", "") if ext.get("class") else ""
    _area = ext.get("area", "") if ext.get("area") else ""
    _year = ext.get("year", "") if ext.get("year") else ""
    _lang = ext.get("lang", "") if ext.get("lang") else ""
    _by = ext.get("by", "") if ext.get("by") else ""

    await OmniBox.log("info", f"[category] cid={cid}, page={page}")

    try:
        # 原脚本使用HTML页面解析
        url = f"{HOST}/vod/show/id/{cid}{_type}{__class}{_area}{_year}{_lang}{_by}/page/{page}"
        res = await OmniBox.request(url, {"method": "GET", "headers": _headers()})

        if res.get("statusCode") != 200:
            return {"list": [], "page": page, "pagecount": 1, "total": 0}

        html = res.get("body", "")
        # 解析内嵌 JSON 数据 - 直接从HTML提取vod对象
        idx = html.find('videoList')
        if idx < 0:
            return {"list": [], "page": page, "pagecount": 1, "total": 0}

        # 从 videoList 开始，找所有 vodId
        snippet = html[idx:idx+50000]
        # 解码转义字符
        decoded = snippet.replace('\\"', '"').replace('\\\\', '\\')

        # 找到 "list":[ 的位置
        list_idx = decoded.find('"list":[')
        if list_idx < 0:
            return {"list": [], "page": page, "pagecount": 1, "total": 0}

        # 从 list:[ 开始，提取所有视频对象
        list_start = list_idx + 8  # 跳过 "list":[，指向第一个元素
        data_list = []

        # 用正则匹配每个视频对象（找 {"vodId":...} 这样的对象）
        # 方法：从 list_start 开始，找所有 { } 包裹的内容
        depth = 1  # 已经在 "list":[ 内部的 [ 之后
        obj_start = -1
        for i in range(list_start, len(decoded)):
            c = decoded[i]
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    break
            elif c == '{' and depth == 1:  # 第一层 { 是视频对象开始
                obj_start = i
            elif c == '}' and obj_start >= 0 and depth == 1:
                # 提取完整对象
                obj_str = decoded[obj_start:i+1]
                try:
                    obj = json.loads(obj_str)
                    # 检查是否有 vodId
                    if 'vodId' in obj:
                        data_list.append(obj)
                except:
                    pass
                obj_start = -1
        
        if not data_list:
            return {"list": [], "page": page, "pagecount": 1, "total": 0}

        list_items = [_parse_vod(item) for item in data_list]

        return {"list": list_items, "page": page, "pagecount": 999, "total": len(data_list)}
    except Exception as e:
        await OmniBox.log("error", f"[category] 失败: {e}")
        return {"list": [], "page": page, "pagecount": 1, "total": 0}


async def detail(params, context):
    """视频详情"""
    video_id = params.get("videoId", "")
    if not video_id:
        return {"list": []}
    
    await OmniBox.log("info", f"[detail] videoId={video_id}")
    
    try:
        t = str(int(time.time() * 1000))
        sign_data = f"id={video_id}&key={API_KEY}&t={t}"
        sign = _sign(sign_data)
        
        res = await OmniBox.request(f"{HOST}/api/mw-movie/anonymous/video/detail?id={video_id}", {
            "method": "GET",
            "headers": {**_headers(), "t": t, "sign": sign}
        })
        
        if res.get("statusCode") != 200:
            return {"list": []}
        
        data = json.loads(res.get("body", "{}")).get("data", {})
        
        # 构建播放源
        episodes = []
        for item in data.get("episodeList", []):
            name = item.get("name", "")
            nid = item.get("nid", "")
            play_id = f"{video_id}/{nid}"
            episodes.append({"name": name, "playId": play_id})
        
        vod_play_sources = []
        if episodes:
            vod_play_sources.append({"name": "老僧酿酒", "episodes": episodes})
        
        item = {
            "vod_id": video_id,
            "vod_name": data.get("vodName", ""),
            "vod_pic": data.get("vodPic", ""),
            "type_name": data.get("typeName", ""),
            "vod_remarks": data.get("vodRemarks", ""),
            "vod_year": data.get("vodYear", ""),
            "vod_area": data.get("vodArea", ""),
            "vod_actor": data.get("vodActor", ""),
            "vod_director": data.get("vodDirector", ""),
            "vod_content": data.get("vodContent", ""),
            "vod_play_sources": vod_play_sources,
        }
        
        return {"list": [item]}
    except Exception as e:
        await OmniBox.log("error", f"[detail] 失败: {e}")
        return {"list": []}


async def search(params, context):
    """搜索"""
    keyword = (params.get("keyword") or params.get("wd") or "").strip()
    page = int(params.get("page") or 1)

    if not keyword:
        return {"page": 1, "pagecount": 0, "total": 0, "list": []}

    await OmniBox.log("info", f"[search] keyword={keyword}, page={page}")

    try:
        t = str(int(time.time() * 1000))
        sign_data = f"keyword={keyword}&pageNum={page}&pageSize=12&key={API_KEY}&t={t}"
        sign = _sign(sign_data)

        # 对URL参数进行编码
        from urllib.parse import quote
        encoded_keyword = quote(keyword)
        url = f"{HOST}/api/mw-movie/anonymous/video/searchByWord?keyword={encoded_keyword}&pageNum={page}&pageSize=12"

        res = await OmniBox.request(
            url,
            {"method": "GET", "headers": {**_headers(), "t": t, "sign": sign}}
        )

        if res.get("statusCode") != 200:
            return {"page": 1, "pagecount": 0, "total": 0, "list": []}

        data = json.loads(res.get("body", "{}")).get("data", {}).get("result", {}).get("list", [])
        list_items = [_parse_vod(item) for item in data]

        return {"page": page, "pagecount": 1, "total": len(list_items), "list": list_items}
    except Exception as e:
        await OmniBox.log("error", f"[search] 失败: {e}")
        return {"page": 1, "pagecount": 0, "total": 0, "list": []}


async def play(params, context):
    """播放"""
    play_id = params.get("playId", "")
    flag = params.get("flag", "")
    
    if not play_id:
        return {"urls": []}
    
    await OmniBox.log("info", f"[play] playId={play_id}")
    
    try:
        # play_id 格式: {vodId}/{nid}
        parts = play_id.split("/")
        if len(parts) != 2:
            return {"urls": [{"name": "播放", "url": ERROR_URL}]}
        
        _id = parts[0]
        _nid = parts[1]
        
        t = str(int(time.time() * 1000))
        sign_data = f"id={_id}&nid={_nid}&key={API_KEY}&t={t}"
        sign = _sign(sign_data)
        
        res = await OmniBox.request(
            f"{HOST}/api/mw-movie/anonymous/v2/video/episode/url?id={_id}&nid={_nid}",
            {"method": "GET", "headers": {**_headers(), "t": t, "sign": sign}}
        )
        
        if res.get("statusCode") == 200:
            data = json.loads(res.get("body", "{}")).get("data", {})
            play_url = data.get("list", [{}])[0].get("url", ERROR_URL)
        else:
            play_url = ERROR_URL
        
        return {
            "urls": [{"name": "播放", "url": play_url}],
            "flag": flag,
            "header": {"User-Agent": UA},
            "parse": 0,
        }
    except Exception as e:
        await OmniBox.log("error", f"[play] 失败: {e}")
        return {"urls": [{"name": "播放", "url": ERROR_URL}]}


if __name__ == "__main__":
    run({
        "home": home,
        "category": category,
        "detail": detail,
        "search": search,
        "play": play
    })
