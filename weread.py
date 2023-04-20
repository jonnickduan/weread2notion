

import argparse
import json
import logging
import time
from notion_client import Client
import requests
from requests.utils import cookiejar_from_dict
from http.cookies import SimpleCookie
from datetime import datetime

WEREAD_URL = "https://weread.qq.com/"
WEREAD_NOTEBOOKS_URL = "https://i.weread.qq.com/user/notebooks"
WEREAD_BOOKMARKLIST_URL = "https://i.weread.qq.com/book/bookmarklist"
WEREAD_CHAPTER_INFO = "https://i.weread.qq.com/book/chapterInfos"


def parse_cookie_string(cookie_string):
    cookie = SimpleCookie()
    cookie.load(cookie_string)
    cookies_dict = {}
    cookiejar = None
    for key, morsel in cookie.items():
        cookies_dict[key] = morsel.value
        cookiejar = cookiejar_from_dict(
            cookies_dict, cookiejar=None, overwrite=True
        )
    return cookiejar


def get_bookmark_list(title, bookId, cover, sort, author, chapter):
    """获取我的划线"""
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOKMARKLIST_URL, params=params)
    if r.ok:
        datas = r.json()["updated"]
        children = []
        if chapter != None:
            # 添加目录
            children.append(get_table_of_contents())
            datas = sorted(datas, key=lambda x: (x.get("chapterUid",1), x.get("range")))
            d = {}
            print(chapter)
            for data in datas:
                chapterUid = data.get("chapterUid",1)
                if (chapterUid not in d):
                    d[chapterUid] = []
                d[chapterUid].append(data)
            for key, value in d .items():
                if key in chapter:
                    children.append(get_heading(
                        chapter.get(key).get("level"), chapter.get(key).get("title")))
                for i in value:
                    children.append(get_callout(
                        i.get("markText"), data.get("style"), i.get("colorStyle")))
        else:
            for data in datas:
                children.append(get_callout(data.get("markText"),
                                data.get("style"), data.get("colorStyle")))
        insert_to_notion(title, bookId, cover, sort, author, children)


def get_table_of_contents():
    """获取目录"""
    return {
        "type": "table_of_contents",
        "table_of_contents": {
            "color": "default"
        }
    }


def get_heading(level, content):
    if level == 1:
        heading = "heading_1"
    elif level == 2:
        heading = "heading_2"
    else:
        heading = "heading_3"
    return {
        "type": heading,
        heading: {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content,
                }
            }],
            "color": "default",
            "is_toggleable": False
        }
    }


def get_callout(content, style, colorStyle):
    # 根据不同的划线样式设置不同的emoji 直线type=0 背景颜色是1 波浪线是2
    emoji = "🌟"
    if style == 0:
        emoji = "💡"
    elif style == 1:
        emoji = "⭐"
    color = "default"
    # 根据划线颜色设置文字的颜色
    if colorStyle == 1:
        color = "red"
    elif colorStyle == 2:
        color = "purple"
    elif colorStyle == 3:
        color = "blue"
    elif colorStyle == 4:
        color = "green"
    elif colorStyle == 5:
        color = "yellow"
    return {
        "type": "callout",
        "callout": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content,
                }
            }],
            "icon": {
                "emoji": emoji
            },
            "color": color
        }
    }


def check(bookId):
    """检查是否已经插入过 如果已经插入了就删除"""
    time.sleep(0.3)
    filter = {
        "property": "BookId",
        "rich_text": {
            "equals": bookId
        }
    }
    response = client.databases.query(database_id=database_id, filter=filter)
    for result in response["results"]:
        time.sleep(0.3)
        client.blocks.delete(block_id=result["id"])


def get_chapter_info(bookId):
    """获取章节信息"""
    body = {
        'bookIds': [bookId],
        'synckeys': [0],
        'teenmode': 0
    }
    url = 'https://i.weread.qq.com/book/chapterInfos'
    r = session.post(url, json=body)
    if r.ok and "data" in r.json() and len(r.json()["data"]) == 1 and "updated" in r.json()["data"][0]:
        update = r.json()["data"][0]["updated"]
        return {item["chapterUid"]: item for item in update}
    return None


def insert_to_notion(bookName, bookId, cover, date, author, children):
    """插入到notion"""
    time.sleep(0.3)
    parent = {
        "database_id": database_id,
        "type": "database_id"
    }

    properties = {
        "BookName": {"title": [{"type": "text", "text": {"content": bookName}}]},
        "BookId": {"rich_text": [{"type": "text", "text": {"content": bookId}}]},
        "Author": {"rich_text": [{"type": "text", "text": {"content": author}}]},
        "Date": {"date": {"start": date.strftime("%Y-%m-%d %H:%M:%S"), "time_zone": "Asia/Shanghai"}},
        "Cover": {"files": [{"type": "external", "name": "Cover", "external": {"url": cover}}]},

    }
    icon = {
        "type": "external",
        "external": {
            "url": cover
        }
    }
    # notion api 限制100个block
    response = client.pages.create(
        parent=parent,icon=icon, properties=properties, children=children[0:100])
    id = response["id"]
    for i in range(1, len(children)//100+1):
        time.sleep(0.3)
        response = client.blocks.children.append(
            block_id=id, children=children[i*100:(i+1)*100])
    return id


def get_notebooklist():
    """获取笔记本列表"""
    r = session.get(WEREAD_NOTEBOOKS_URL)
    books = []
    if r.ok:
        data = r.json()
        books = data["books"]
        books.sort(key=lambda x: x["sort"])
        book = books[0]
        for book in books:
            sort = book["sort"]
            sort = datetime.utcfromtimestamp(sort)
            if date is not None and sort < date :
                continue
                
            title = book["book"]["title"]
            cover = book["book"]["cover"]
            bookId = book["book"]["bookId"]
            author = book["book"]["author"]
            check(bookId)
            chapter = get_chapter_info(bookId)
            get_bookmark_list(title, bookId, cover, sort, author, chapter)


def get_date():
    """获取database中的最新时间"""
    filter = {
        "property": "Date",
        "date": {
            "is_not_empty": True
        }
    }
    sorts = [
        {
            "property": "Date",
            "direction": "descending",
        }
    ]
    response = client.databases.query(
        database_id=database_id, filter=filter, sorts=sorts, page_size=1)
    if (len(response["results"]) == 1):
        date = datetime.fromisoformat(
            response["results"][0]["properties"]["Date"]["date"]["start"]).replace(tzinfo=None)
        return date
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("weread_cookie")
    parser.add_argument("notion_token")
    parser.add_argument("database_id")
    options = parser.parse_args()
    weread_cookie = options.weread_cookie
    database_id = options.database_id
    notion_token = options.notion_token
    session = requests.Session()
    session.cookies = parse_cookie_string(weread_cookie)
    client = Client(
        auth=notion_token,
        log_level=logging.ERROR
    )
    session.get(WEREAD_URL)
    date = get_date()
    get_notebooklist()
