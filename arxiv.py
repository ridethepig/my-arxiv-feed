import argparse
import datetime
import hashlib
import os
import os.path as path
import pickle
import time
from dataclasses import dataclass

import lxml.etree as etree
import markdown
import requests

import ArxivCategory
import tencent_translator
import utils

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


@dataclass
class RSSItem:
    title: str
    link: str
    desc: str
    author: str

    def get_short_id(self) -> str:
        return self.link.strip("/").split("/")[-1]


@dataclass
class RSSMeta:
    title: str
    description: str
    update_date: str
    subject: str


@dataclass
class ATOMItem:
    id: str
    updated: str
    published: str
    title: str
    summary: str
    author: list[str]
    comment: str | None
    link_abs: str
    link_pdf: str
    category: list[str]
    primary_category: str

    def get_short_id(self) -> str:
        if not hasattr(self, "id_short"):
            self.id_short = self.id.strip("/").split("/")[-1]
        return self.id_short

    def is_update(self) -> bool:
        return self.updated != self.published

    def to_markdown(self, translations=None):
        title_trans = None
        if translations is not None:
            if self.get_short_id() in translations:
                title_trans = translations[self.get_short_id()][0]
        
        return f"""\
### {self.title}

> **{"标题" if title_trans is None else title_trans}**  
> Link: [{self.get_short_id()}]({self.link_abs})  
> Comments: {self.comment}  
> Category: **{self.primary_category}**, {", ".join(self.category)}  
> Authors: {", ".join(self.author)}  
> Date: {self.updated}{f" (Published @{self.published})" if self.is_update() else ""}  

***摘要:*** 

**这是摘要**

***Abstract:***

{utils.pre_process_abstract(self.summary)}

"""


def parse_atom(atom_str: str) -> list[ATOMItem]:
    atom = etree.XML(atom_str)
    nsmap = atom.nsmap
    nsmap["ns"] = nsmap[None]
    nsmap["arxiv"] = "http://arxiv.org/schemas/atom"
    del nsmap[None]  # none key is not allow in lxml xpath
    entries = atom.xpath("/ns:feed/ns:entry", namespaces=nsmap)
    query_results = []
    for entry in entries:
        id = entry.xpath("./ns:id", namespaces=nsmap)[0].text
        updated = entry.xpath("./ns:updated", namespaces=nsmap)[0].text
        published = entry.xpath("./ns:published", namespaces=nsmap)[0].text
        title = entry.xpath("./ns:title", namespaces=nsmap)[0].text
        summary = entry.xpath("./ns:summary", namespaces=nsmap)[0].text

        comment_elems = entry.xpath("./arxiv:comment", namespaces=nsmap)
        comment = None if len(comment_elems) == 0 else comment_elems[0].text

        author_elems = entry.xpath("./ns:author/ns:name", namespaces=nsmap)
        authors = [elem.text for elem in author_elems]

        link_abs = entry.xpath("./ns:link[@rel='alternate']", namespaces=nsmap)[0].attrib["href"]
        link_pdf = entry.xpath("./ns:link[@title='pdf']", namespaces=nsmap)[0].attrib["href"]

        primary_category = entry.xpath("./arxiv:primary_category",
                                       namespaces=nsmap)[0].attrib["term"]
        category_elems = entry.xpath("./ns:category", namespaces=nsmap)
        categories = [elem.attrib["term"] for elem in category_elems]

        atom_item = ATOMItem(
            id=id,
            updated=updated,
            published=published,
            title=title.replace('\n', ''),
            summary=summary,
            author=authors,
            comment=comment,
            link_abs=link_abs,
            link_pdf=link_pdf,
            category=categories,
            primary_category=primary_category,
        )
        query_results.append(atom_item)
    return query_results


def parse_rss(rss_str: str) -> tuple[RSSMeta, list[RSSItem]]:
    xml = etree.XML(rss_str)
    nsmap = xml.nsmap
    nsmap["ns"] = nsmap[None]
    del nsmap[None]  # none key is not allow in lxml xpath
    title = xml.xpath("/rdf:RDF/ns:channel/ns:title", namespaces=nsmap)[0].text
    description = xml.xpath("/rdf:RDF/ns:channel/ns:description", namespaces=nsmap)[0].text
    update_date = xml.xpath("/rdf:RDF/ns:channel/dc:date", namespaces=nsmap)[0].text
    subject = xml.xpath("/rdf:RDF/ns:channel/dc:subject", namespaces=nsmap)[0].text

    if VERBOSE:
        print(f"""\
MetaData
  Title - {title}
  Desc - {description}
  Date - {update_date}
  Subject - {subject}
""")
    rss_metadata = RSSMeta(title=title, description=description,
                           update_date=update_date, subject=subject)

    items = xml.xpath("/rdf:RDF/ns:item", namespaces=nsmap)
    print(f"{len(items)} Updates")

    rss_results = []
    for item in items:
        _title = item.xpath("./ns:title", namespaces=nsmap)[0].text
        _link = item.xpath("./ns:link", namespaces=nsmap)[0].text
        _description = item.xpath("./ns:description", namespaces=nsmap)[0].text
        _authors = item.xpath("./dc:creator", namespaces=nsmap)[0].text
        data = RSSItem(_title, _link, _description, _authors)
        rss_results.append(data)
        if VERBOSE:
            print(f"  {_title}")
    return rss_metadata, rss_results


def query_rss(subcategory="cs", force=False) -> str:
    rss_url = RSS_BASE + subcategory
    rss_file_name = f"{datetime.date.today()}-{subcategory}.xml"
    rss_file_path = path.join(CACHE_FETCH, rss_file_name)
    if path.exists(rss_file_path) and not force:
        print(f"[INFO] use cached `{rss_file_path}`")
        with open(rss_file_path, "rb") as f:
            rss_str = f.read()
        return rss_str
    print(f"[INFO] getting rss from {rss_url}")
    rss_resp = requests.get(rss_url)
    with open(rss_file_path, "w") as f:
        f.write(rss_resp.text)
    print(f"[INFO] rss got from {rss_url}")
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
            print(f"[INFO] use cached `{atom_file_path}`")
            with open(atom_file_path, "rb") as f:
                atom_str = f.read()
                atom_strs.append(atom_str)
            continue

        params = {"id_list": id_list_str, "max_results": items_per_req}
        print(f"[INFO] query for {len(id_list_slice)} items")
        atom_resp = requests.get(API_BASE, params=params)
        with open(atom_file_path, "w") as f:
            f.write(atom_resp.text)
        print(f"[INFO] query done from {atom_resp.url}")
        atom_strs.append(atom_resp.text.encode())
        time.sleep(req_interval)
    return atom_strs


def generate(cate_list: list[str], tag: str, args):
    STARTTIME = utils.get_local_time(datetime.datetime.now())
    date_filename = STARTTIME.strftime("%y%m%d.%I%p")
    translations: dict[str, list[str | None]] = None

    print(f"[STATUS] Querying RSS for Category: {cate_list}")
    id_list = []
    for cate in cate_list:
        rss_str = query_rss(cate)
        rss_meta, rss_items = parse_rss(rss_str)
        id_list += [item.get_short_id() for item in rss_items]
    id_list = list(set(id_list))
    id_list.sort(reverse=True)

    print(f"[STATUS] Collecting details for {len(id_list)} papers")
    atom_strs = query_atom(id_list, items_per_req=20, force=False)
    atom_items: list[ATOMItem] = []
    for atom_str in atom_strs:
        atom_items += parse_atom(atom_str)
    cate2item: dict[str, list[ATOMItem]] = {}
    for item in atom_items:
        item.title = utils.pre_proc_title(item.title)
        if item.primary_category not in cate2item:
            cate2item[item.primary_category] = []
        cate2item[item.primary_category].append(item)
    if VERBOSE:
        print("; ".join([f"{cate}:{len(cate2item[cate])}" for cate in cate2item]))

    if args.translate_title:
        if path.exists(CACHE_TRANS):
            translations = utils.pkl_load(CACHE_TRANS)
            print(f"[INFO] Loaded translation cache file `{CACHE_TRANS}`")
        else:
            translations = {}

        print(f"[STATUS] Translating titles")
        for item in atom_items:
            if item.get_short_id() not in translations:
                translations[item.get_short_id()] = [None, None]
            if translations[item.get_short_id()][0] is not None:
                continue
            title_trans = tencent_translator.translate(item.title)
            if title_trans is None:
                utils.pkl_dump(translations, CACHE_TRANS)
                raise Exception
            else:
                translations[item.get_short_id()][0] = title_trans
        utils.pkl_dump(translations, CACHE_TRANS)

    print(f"[STATUS] Generating markdown")
    md_file_name = f"Feed-{date_filename}-{tag}.md"
    md_file_path = path.join(CACHE_GEN, md_file_name)
    with open(md_file_path, "w") as f:
        f.write(f"""\
# Arxiv Feed \\[{tag}\\]
> Published @ {rss_meta.update_date}
> Fetched @ {STARTTIME.strftime("%Y-%m-%d %H:%M")} {datetime.datetime.tzname(STARTTIME)}  

""")
        for cate in cate2item:
            if cate not in ArxivCategory.CS_CATEGORY:
                continue
            f.write(f"""## {cate}, {ArxivCategory.ALL_CATEGORY[cate]}\n""")
            for item in cate2item[cate]:
                f.write(item.to_markdown(translations))
        for cate in cate2item:
            if cate not in ArxivCategory.CS_CATEGORY:
                skips = [item.get_short_id() for item in cate2item[cate]]
                f.write(f"> SKIP {cate} {','.join(skips)}  \n")

    print("[STATUS] Convert result to HTML")
    with open(md_file_path, "r", encoding='utf-8') as input_file:
        text = input_file.read()
    html = markdown.markdown(text)
    html_file_name = f"Feed-{date_filename}-{tag}.html"
    html_file_path = path.join(CACHE_GEN, html_file_name)
    with open(html_file_path, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch feed from arxiv by RSS and its API')
    parser.add_argument('-V', '--verbose', default=False, action='store_true')
    parser.add_argument('-T', '--translate_title', default=False, action='store_true')
    parser.add_argument('-t', '--translate_abs', default=False, action='store_true')
    args = parser.parse_args()
    VERBOSE = args.verbose
    generate(ArxivCategory.SYS_CATEGORY, "SYS", args)
    # generate(ArxivCategory.AI_CATEGORY, "AI")

"""
TODO [] datetime for each item
TODO [] Special character
TODO [] Translate
TODO [] Math
TODO [] Cache to sqlite instead of pickle
"""
