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


def ATOM2MD(metadata: ATOMItem, translations: tuple[str | None, str | None] = (None, None)) -> str:
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


def generate_markdown(cate2item, skip2item, tag, pubtime, fetchtime) -> str:
    import io
    f = io.StringIO()
    f.write(f"""\
# Arxiv Feed \\[{tag}\\]
> Published @ {pubtime}  
> Fetched @ {fetchtime}

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
    result = f.getvalue()
    f.close()
    return result


def generate_from_history(date: str) -> [list[ATOMItem], str]:
    logger.info(f"Retrieving paper back in {date} from database")
    arxivtime = datetime.datetime.strptime(date, "%Y%m%d")
    arxivtime = arxivtime.replace(hour=20, minute=30, tzinfo=utils._arxiv_tz).isoformat()
    id_lists = db.daily_get_by_date(arxivtime)
    atom_items = []
    for arxivid in id_lists:
        meta_item = db.paper_meta_get(arxivid)
        if meta_item is None:
            logger.error(f"record not found {arxivid}")
            continue
        atom_items.append(meta_item)
    return atom_items, arxivtime


def generate_from_query(cate_list: list[str]) -> [list[ATOMItem], str]:
    logger.info(f"Querying RSS for Category: {cate_list}")
    id_list = []
    for cate in cate_list:
        rss_str = query_rss(cate, args.refetch)
        rss_meta, rss_items = parse_rss(rss_str)
        id_list += [item.id_short for item in rss_items]
    id_list = list(set(id_list))
    id_list.sort(reverse=True)

    logger.info(f"Collecting details for {len(id_list)} papers")
    atom_strs = query_atom(id_list, items_per_req=20, force=args.refetch)
    atom_items: list[ATOMItem] = []
    for atom_str in atom_strs:
        atom_items += parse_atom(atom_str)
    for atom_item in atom_items:
        db.daily_set(MainLogItem(atom_item.arxivid, rss_meta.update_date, None))
        db.paper_meta_set(atom_item)
    db.conn.commit()
    return atom_items, rss_meta.update_date


def generate(cate_list: list[str], tag: str, args):
    db.init_db()
    if args.history is not None:
        atom_items, arxivtime = generate_from_history(args.history)
    else:
        atom_items, arxivtime = generate_from_query(cate_list)

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
    arxivdate = utils.get_arxiv_time(arxivtime).strftime("%y%m%d")
    md_filename = f"Feed-{arxivdate}-{tag}.md"
    md_filepath = path.join(CACHE_GEN, md_filename)
    fetchtime = utils.get_local_time(datetime.datetime.now())
    fetchtime = f"""{fetchtime.strftime("%Y-%m-%d %H:%M")} {datetime.datetime.tzname(fetchtime)}"""
    with open(md_filepath, "w") as f:
        f.write(generate_markdown(cate2item, skip2item, tag, arxivtime, fetchtime))

    logger.info("Convert result to HTML")
    with open(md_filepath, "r", encoding='utf-8') as input_file:
        text = input_file.read()
    html = markdown.markdown(text)
    html_filename = f"Feed-{arxivdate}-{tag}.html"
    html_filepath = path.join(CACHE_GEN, html_filename)
    with open(html_filepath, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html)

    logger.info("Finish")
    if not args.no_open_browser:
        webbrowser.open_new_tab(os.path.abspath(html_filepath))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch feed from arxiv by RSS and its API')
    parser.add_argument('-V', '--verbose', default=False, action='store_true')
    parser.add_argument('-r', '--refetch', default=False, action='store_true')
    parser.add_argument('--translate-title', default=False, action='store_true')
    parser.add_argument('--translate-abs', default=False, action='store_true')
    parser.add_argument('--translate-force', default=False, action='store_true')
    parser.add_argument('--no-open-browser', default=False, action='store_true')
    parser.add_argument('--strict', default=False, action='store_true')
    parser.add_argument("--history", type=str)
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
"""
