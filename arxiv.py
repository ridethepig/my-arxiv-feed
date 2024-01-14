import argparse
import datetime
import hashlib
import os
import os.path as path
import pprint
import re
import time
from dataclasses import dataclass

import lxml.etree as etree
import markdown
import requests

import ArxivCategory

CACHE_FETCH = "cache/fetch/"
CACHE_GEN = "cache/gen/"
if not path.exists(CACHE_FETCH):
    os.makedirs(CACHE_FETCH)
if not path.exists(CACHE_GEN):
    os.makedirs(CACHE_GEN)
VERBOSE = False


@dataclass
class RSSItem:
    title: str
    link: str
    desc: str
    author: str


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

    def to_markdown(self):
        return f"""\
### {self.title}
> **Translated title here**  
> Link: [{self.link_abs.strip("/").split("/")[-1]}]({self.link_abs})  
> Comments: {self.comment}  
> Category: **{self.primary_category}**, {", ".join(self.category)}  
> Authors: {", ".join(self.author)}  
> Date: {self.updated}{f" (Published @{self.published})" if self.updated != self.published else ""}  

***摘要:***  
**这是摘要**

***Abstract:***  
{self.summary}
---
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

        link_abs = entry.xpath("./ns:link[@rel='alternate']", namespaces=nsmap)[
            0
        ].attrib["href"]
        link_pdf = entry.xpath("./ns:link[@title='pdf']", namespaces=nsmap)[0].attrib[
            "href"
        ]

        primary_category = entry.xpath("./arxiv:primary_category", namespaces=nsmap)[
            0
        ].attrib["term"]
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
    description = xml.xpath("/rdf:RDF/ns:channel/ns:description", namespaces=nsmap)[
        0
    ].text
    update_date = xml.xpath(
        "/rdf:RDF/ns:channel/dc:date", namespaces=nsmap)[0].text
    subject = xml.xpath("/rdf:RDF/ns:channel/dc:subject",
                        namespaces=nsmap)[0].text
    print(f"""MetaData
  Title - {title}
  Desc - {description}
  Date - {update_date}
  Subject - {subject}
"""
          )
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
    RSS_BASE = "http://arxiv.org/rss/"
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
    QUERY_BASE = "http://export.arxiv.org/api/query"
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
        atom_resp = requests.get(QUERY_BASE, params=params)
        with open(atom_file_path, "w") as f:
            f.write(atom_resp.text)
        print(f"[INFO] query done from {atom_resp.url}")
        atom_strs.append(atom_resp.text.encode())
        time.sleep(req_interval)
    return atom_strs


def pre_process(raw_text: str) -> str:
    return re.sub(r'^ {2}', ' ', raw_text, re.MULTILINE)

def generate(cate_list: list[str], tag: str):
    print(f"Querying RSS for Category: {cate_list}")
    id_list = []
    for cate in cate_list:
        rss_str = query_rss(cate)
        rss_meta, rss_items = parse_rss(rss_str)
        id_list += [item.link.strip("/").split("/")[-1] for item in rss_items]
    id_list = list(set(id_list))
    id_list.sort(reverse=True)

    print(f"Collecting details for {len(id_list)} papers")
    atom_strs = query_atom(id_list, items_per_req=20, force=False)
    atom_items = []
    for atom_str in atom_strs:
        atom_items += parse_atom(atom_str)

    print(f"Generating markdown")
    cate2item = dict()
    for item in atom_items:
        if item.primary_category not in cate2item.keys():
            cate2item[item.primary_category] = []
        cate2item[item.primary_category].append(item)
    if VERBOSE:
        for cate in cate2item.keys():
            print(f"{cate}:{len(cate2item[cate])}; ", end="")
        print("")

    date = datetime.datetime.now().strftime("%Y%m%d.%I%p")
    md_file_name = f"Feed-{date}-{tag}.md"
    md_file_path = path.join(CACHE_GEN, md_file_name)
    with open(md_file_path, "w") as f:
        f.write(f"""\
## Arxiv Feed \\[{tag}\\]
> Fetched @ {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
> Published @ {rss_meta.update_date}

""")
        for atom_item in atom_items:
            f.write(atom_item.to_markdown())
    print("Convert result to HTML")
    with open(md_file_path, "r", encoding='utf-8') as input_file:
        text = input_file.read()
    html = markdown.markdown(text)
    html_file_name = f"Feed-{date}-{tag}.html"
    html_file_path = path.join(CACHE_GEN, html_file_name)
    with open(html_file_path, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Fetch feed from arxiv by RSS and its API')
    parser.add_argument('-V', '--verbose', default=False, action='store_true')
    args = parser.parse_args()
    VERBOSE = args.verbose

    generate(ArxivCategory.SYS_CATEGORY, "SYS")
    # generate(ArxivCategory.AI_CATEGORY, "AI")

"""
TODO
1. Breakline
2. Updated tag
"""
