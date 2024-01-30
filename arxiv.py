import argparse
import datetime
import os
import os.path as path
import time
import webbrowser
from collections import defaultdict

import markdown

import arxivcategory
import db
import tencent_translator
import utils
from arxivdata import ATOMItem, parse_atom, parse_rss
from arxivquery import query_atom, query_rss
from config import CACHE_GEN
from db import MainLogItem, TransItem
from utils import logger


def translate(atom_item: ATOMItem, tr_option: tuple[bool, bool], force=False, delay=0.5) -> tuple[bool, bool]:
    if not tr_option[0] and not tr_option[1]:
        return (None, None)
    _title = 'Title' if tr_option[0] else ''
    _abs = 'Abstract' if tr_option[1] else ''
    logger.debug("Translating %s%s for %s", _title, _abs, atom_item.arxivid)
    trans_cache = db.translation_get(atom_item.arxivid)
    if trans_cache is None:
        trans_cache = TransItem(atom_item.arxivid, None, None)
    if tr_option[0] and (trans_cache.title is None or force):
        trans_cache.title = tencent_translator.translate(atom_item.title)
        if trans_cache.title is None or len(trans_cache.title) == 0:
            db.conn.commit()
            raise Exception
        else:
            db.translation_set(trans_cache)
        time.sleep(delay)
    if tr_option[1] and (trans_cache.abs is None or force):
        summary = utils.pre_process_abstract(atom_item.summary)
        trans_cache.abs = tencent_translator.translate(summary)
        if trans_cache.abs is None or len(trans_cache.abs) == 0:
            db.conn.commit()
            raise Exception
        else:
            db.translation_set(trans_cache)
        time.sleep(delay)
    db.conn.commit()
    return trans_cache.title, trans_cache.abs


def ATOM2MD(metadata: ATOMItem, translations: tuple[str | None, str | None] = (None, None)):
    tr_title, tr_abs = translations
    tr_title = tr_title or "这是标题"
    tr_abs = tr_abs or "这是摘要"

    return f"""\
### {metadata.title}

> **{tr_title}**  
> Link: [{metadata.arxivid}]({metadata.link_abs})  
> Comments: {metadata.comment}  
> Category: **{metadata.primary_category}**, {", ".join(metadata.category)}  
> Authors: {", ".join(metadata.author)}  
> Date: {metadata.updated}{f" (Published @{metadata.published})" if metadata.is_update() else ""}  

**摘要:**

{tr_abs}

**Abstract:**

{utils.pre_process_abstract(metadata.summary)}

"""


def generate(cate_list: list[str], tag: str, args):
    start_time = utils.get_local_time(datetime.datetime.now())
    db.init_db()
    print(db.conn)
    logger.info(f"Querying RSS for Category: {cate_list}")
    id_list = []
    for cate in cate_list:
        rss_str = query_rss(cate, args.refetch)
        rss_meta, rss_items = parse_rss(rss_str)
        id_list += [item.id_short for item in rss_items]
    id_list = list(set(id_list))
    id_list.sort(reverse=True)
    for arxivid in id_list:
        db.daily_set(MainLogItem(arxivid, rss_meta.update_date, None))
    db.conn.commit()

    logger.info(f"Collecting details for {len(id_list)} papers")
    atom_strs = query_atom(id_list, items_per_req=20, force=args.refetch)
    atom_items: list[ATOMItem] = []
    for atom_str in atom_strs:
        atom_items += parse_atom(atom_str)
    for atom_item in atom_items:
        db.paper_meta_set(atom_item)
    db.conn.commit()
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
    date_filename = utils.get_arxiv_time(rss_meta.update_date).strftime("%y%m%d")
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
                f.write(ATOM2MD(item, translations))
        for cate in skip2item:
            skips = [item.arxivid for item in skip2item[cate]]
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
