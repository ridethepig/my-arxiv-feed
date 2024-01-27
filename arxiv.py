import argparse
import datetime
import hashlib
import os
import os.path as path
import time
import webbrowser
from collections import defaultdict

import markdown
import requests

import ArxivCategory
import tencent_translator
import utils
from arxivdata import ATOMItem, RSSItem, RSSMeta
from arxivdata import parse_atom, parse_rss
from utils import logger

RSS_BASE = "http://arxiv.org/rss/"
API_BASE = "http://export.arxiv.org/api/query"
CACHE_FETCH = "cache/fetch/"
CACHE_GEN = "cache/gen/"
CACHE_TRANS = "cache/trans.pkl"
if not path.exists(CACHE_FETCH):
    os.makedirs(CACHE_FETCH)
if not path.exists(CACHE_GEN):
    os.makedirs(CACHE_GEN)
VERBOSE = False
STARTTIME = None


def query_rss(subcategory="cs", force=False) -> str:
    rss_url = RSS_BASE + subcategory
    rss_file_name = f"{datetime.date.today()}-{subcategory}.xml"
    rss_file_path = path.join(CACHE_FETCH, rss_file_name)
    if path.exists(rss_file_path) and not force:
        logger.info(f"use cached `{rss_file_path}`")
        with open(rss_file_path, "rb") as f:
            rss_str = f.read()
        return rss_str
    logger.info(f"getting rss from {rss_url}")
    rss_resp = requests.get(rss_url)
    with open(rss_file_path, "w") as f:
        f.write(rss_resp.text)
    logger.info(f"rss got from {rss_url}")
    return rss_resp.text.encode()


def query_atom(id_list, items_per_req=20, force=False, req_interval=3):
    start = 0
    atom_strs = []
    while start < len(id_list):
        id_list_slice = id_list[start: start + items_per_req]
        start += items_per_req
        id_list_str = ",".join(id_list_slice)
        id_list_hash = hashlib.sha256(id_list_str.encode()).hexdigest()
        atom_file_name = f"{datetime.date.today()}-pagesize{items_per_req}-{id_list_hash}.atom"
        atom_file_path = path.join(CACHE_FETCH, atom_file_name)

        if path.exists(atom_file_path) and not force:
            logger.info(f"use cached `{atom_file_path}`")
            with open(atom_file_path, "rb") as f:
                atom_str = f.read()
                atom_strs.append(atom_str)
            continue

        params = {"id_list": id_list_str, "max_results": items_per_req}
        logger.info(f"query for {len(id_list_slice)} items")
        atom_resp = requests.get(API_BASE, params=params)
        with open(atom_file_path, "w") as f:
            f.write(atom_resp.text)
        logger.info(f"query done from {atom_resp.url}")
        atom_strs.append(atom_resp.text.encode())
        time.sleep(req_interval)
    return atom_strs


def generate(cate_list: list[str], tag: str, args):
    from database import Trslt
    STARTTIME = utils.get_local_time(datetime.datetime.now())
    translations: dict[str, list[str | None]] = None

    logger.info(f"Querying RSS for Category: {cate_list}")
    id_list = []
    for cate in cate_list:
        rss_str = query_rss(cate)
        rss_meta, rss_items = parse_rss(rss_str)
        id_list += [item.id_short for item in rss_items]
    id_list = list(set(id_list))
    id_list.sort(reverse=True)

    date_filename = utils.get_arxiv_time(rss_meta.update_date).strftime("%y%m%d")

    logger.info(f"Collecting details for {len(id_list)} papers")
    atom_strs = query_atom(id_list, items_per_req=20, force=False)
    atom_items: list[ATOMItem] = []
    for atom_str in atom_strs:
        atom_items += parse_atom(atom_str)
    cate2item: dict[str, list[ATOMItem]] = defaultdict(list)
    skip2item: dict[str, list[ATOMItem]] = defaultdict(list)
    for item in atom_items:
        item.title = utils.pre_proc_title(item.title)
        if args.strict:
            if item.primary_category not in cate_list:
                skip2item[item.primary_category].append(item)
                continue
        if item.primary_category not in ArxivCategory.CS_CATEGORY:
            skip2item[item.primary_category].append(item)
            continue
        cate2item[item.primary_category].append(item)
    logger.debug("; ".join([f"{cate}:{len(cate2item[cate])}" for cate in cate2item]))

    if args.translate_title:
        if path.exists(CACHE_TRANS):
            translations = utils.pkl_load(CACHE_TRANS)
            logger.info(f"Loaded translation cache file `{CACHE_TRANS}`")
        else:
            translations = {}

        logger.info(f"Translating titles")
        for item in atom_items:
            if item.id_short not in translations:
                translations[item.id_short] = [None, None]
            if translations[item.id_short][0] is not None:
                continue
            title_trans = tencent_translator.translate(item.title)
            if title_trans is None or len(title_trans) == 0:
                utils.pkl_dump(translations, CACHE_TRANS)
                raise Exception
            else:
                translations[item.id_short][0] = title_trans
        utils.pkl_dump(translations, CACHE_TRANS)

    logger.info(f"Generating markdown")
    md_file_name = f"Feed-{date_filename}-{tag}.md"
    md_file_path = path.join(CACHE_GEN, md_file_name)
    with open(md_file_path, "w") as f:
        f.write(f"""\
# Arxiv Feed \\[{tag}\\]
> Published @ {rss_meta.update_date}
> Fetched @ {STARTTIME.strftime("%Y-%m-%d %H:%M")} {datetime.datetime.tzname(STARTTIME)}  

""")
        for cate in cate2item:
            f.write(f"""## {cate}, {ArxivCategory.ALL_CATEGORY[cate]}\n""")
            for item in cate2item[cate]:
                f.write(item.to_markdown(translations))
        for cate in skip2item:
            skips = [item.id_short for item in skip2item[cate]]
            f.write(f"> SKIP {cate} {','.join(skips)}  \n")

    print("[STATUS] Convert result to HTML")
    with open(md_file_path, "r", encoding='utf-8') as input_file:
        text = input_file.read()
    html = markdown.markdown(text)
    html_file_name = f"Feed-{date_filename}-{tag}.html"
    html_file_path = path.join(CACHE_GEN, html_file_name)
    with open(html_file_path, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html)

    if not args.no_open_browser:
        webbrowser.open_new_tab(os.path.abspath(html_file_path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch feed from arxiv by RSS and its API')
    parser.add_argument('-V', '--verbose', default=False, action='store_true')
    parser.add_argument('-T', '--translate-title', default=False, action='store_true')
    parser.add_argument('-t', '--translate-abs', default=False, action='store_true')
    parser.add_argument('--no-open-browser', default=False, action='store_true')
    parser.add_argument('--strict', default=False, action='store_true')
    args = parser.parse_args()
    if args.verbose:
        utils.logger_init(utils.logging.DEBUG)
    else:
        utils.logger_init(utils.logging.INFO)
    generate(ArxivCategory.SYS_CATEGORY, "SYS", args)
    # generate(ArxivCategory.AI_CATEGORY, "AI")

"""
TODO [] datetime for each item
TODO [] Special character
TODO [] Translate
TODO [] Math
TODO [] Cache to sqlite instead of pickle
"""
