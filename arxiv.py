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

import arxivcategory
import tencent_translator
import utils
from arxivdata import ATOMItem, parse_atom, parse_rss
from database import translation_get, translation_save
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


def query_rss(subcategory="cs", force=False) -> str:
    rss_url = RSS_BASE + subcategory
    rss_file_name = f"{datetime.date.today()}-{subcategory}.xml"
    rss_file_path = path.join(CACHE_FETCH, rss_file_name)
    if path.exists(rss_file_path) and not force:
        logger.warning(f"use cached `{rss_file_path}`")
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
            logger.warning(f"use cached `{atom_file_path}`")
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


def translate(atom_item: ATOMItem, tr_option: tuple[bool, bool], force=False, delay=0.5) -> tuple[bool, bool]:
    if not tr_option[0] and not tr_option[1]:
        return (None, None)
    logger.debug(f"Translating for {atom_item.id_short}, switch (title, abs)={tr_option}")
    tr_title, tr_abs = translation_get(atom_item.id_short)
    if tr_option[0] and (tr_title is None or force):
        tr_title = tencent_translator.translate(atom_item.title)
        if tr_title is None or len(tr_title) == 0:
            raise Exception
        else:
            translation_save(atom_item.id_short, title=tr_title)
        time.sleep(delay)
    if tr_option[1] and (tr_abs is None or force):
        summary = utils.pre_process_abstract(atom_item.summary)
        tr_abs = tencent_translator.translate(summary)
        if tr_abs is None or len(tr_abs) == 0:
            raise Exception
        else:
            translation_save(atom_item.id_short, abstract=tr_abs)
        time.sleep(delay)

    return tr_title, tr_abs


def generate(cate_list: list[str], tag: str, args):
    start_time = utils.get_local_time(datetime.datetime.now())

    logger.info(f"Querying RSS for Category: {cate_list}")
    id_list = []
    for cate in cate_list:
        rss_str = query_rss(cate, args.refetch)
        rss_meta, rss_items = parse_rss(rss_str)
        id_list += [item.id_short for item in rss_items]
    id_list = list(set(id_list))
    id_list.sort(reverse=True)

    date_filename = utils.get_arxiv_time(rss_meta.update_date).strftime("%y%m%d")

    logger.info(f"Collecting details for {len(id_list)} papers")
    atom_strs = query_atom(id_list, items_per_req=20, force=args.refetch)
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
        if item.primary_category not in arxivcategory.CS_CATEGORY:
            skip2item[item.primary_category].append(item)
            continue
        cate2item[item.primary_category].append(item)
    logger.debug("; ".join([f"{cate}:{len(cate2item[cate])}" for cate in cate2item]))

    logger.info(f"Generating markdown")
    md_file_name = f"Feed-{date_filename}-{tag}.md"
    md_file_path = path.join(CACHE_GEN, md_file_name)
    with open(md_file_path, "w") as f:
        f.write(f"""\
# Arxiv Feed \\[{tag}\\]
> Published @ {rss_meta.update_date}
> Fetched @ {start_time.strftime("%Y-%m-%d %H:%M")} {datetime.datetime.tzname(start_time)}  

""")
        for cate in cate2item:
            f.write(
                f"""## {cate}, {arxivcategory.ALL_CATEGORY[cate]}\n> {len(cate2item[cate])} papers today\n""")
            for item in cate2item[cate]:
                translations = translate(
                    item, (args.translate_title, args.translate_abs), args.translate_force)
                f.write(item.to_markdown(translations))
        for cate in skip2item:
            skips = [item.id_short for item in skip2item[cate]]
            f.write(f"> SKIP {cate} {','.join(skips)}  \n")

    logger.info("Convert result to HTML")
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
    parser.add_argument('-r', '--refetch', default=False, action='store_true')
    parser.add_argument('--translate-title', default=False, action='store_true')
    parser.add_argument('--translate-abs', default=False, action='store_true')
    parser.add_argument('--translate-force', default=False, action='store_true')
    parser.add_argument('--no-open-browser', default=False, action='store_true')
    parser.add_argument('--strict', default=False, action='store_true')
    args = parser.parse_args()
    if args.verbose:
        utils.logger_init(utils.logging.DEBUG)
    else:
        utils.logger_init(utils.logging.INFO)
    generate(arxivcategory.SYS_CATEGORY, "SYS", args)
    # generate(ArxivCategory.AI_CATEGORY, "AI")

"""
TODO [] Special character
TODO [] Math
TODO [] Cache to sqlite instead of pickle
"""
