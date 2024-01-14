import ArxivCategory
import pprint
import datetime
import hashlib
import os.path as path
import time
from dataclasses import dataclass

import lxml.etree as etree
import requests


@dataclass
class RSSItem:
    title: str
    link: str
    desc: str
    author: str


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


def parse_rss(rss_str: str) -> list[RSSItem]:
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
    print("MetaData")
    print(
        f"  Title - {title}\n"
        f"  Desc - {description}\n"
        f"  Date - {update_date}\n"
        f"  Subject - {subject}"
    )

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
        print(f"  {_title}")
    return rss_results


def query_rss(subcategory="cs", force=False) -> str:
    RSS_BASE = "http://arxiv.org/rss/"
    rss_url = RSS_BASE + subcategory
    rss_file = f"data/{datetime.date.today()}-{subcategory}.xml"
    if path.exists(rss_file) and not force:
        print(f"[INFO] use cached `{rss_file}`")
        with open(rss_file, "rb") as f:
            rss_str = f.read()
        return rss_str
    print(f"[INFO] getting rss from {rss_url}")
    rss_resp = requests.get(rss_url)
    with open(rss_file, "w") as f:
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
        query_cache_file = f"data/{datetime.date.today()}-pagesize{items_per_req}-{id_list_hash}.atom"

        if path.exists(query_cache_file) and not force:
            print(f"[INFO] use cached `{query_cache_file}`")
            with open(query_cache_file, "rb") as f:
                atom_str = f.read()
                atom_strs.append(atom_str)
            continue

        params = {"id_list": id_list_str, "max_results": items_per_req}
        print(f"[INFO] query for {len(id_list_slice)} items")
        atom_resp = requests.get(QUERY_BASE, params=params)
        with open(query_cache_file, "w") as f:
            f.write(atom_resp.text)
        print(f"[INFO] query done from {atom_resp.url}")
        atom_strs.append(atom_resp.text.encode())
        time.sleep(req_interval)
    return atom_strs


def generate_markdown(item: ATOMItem):
    template = f"""\
### {item.title}
> **Translated title here**  
> Link: [{item.link_abs.strip("/").split("/")[-1]}]({item.link_abs})  
> Comments: {item.comment}  
> Category: **{item.primary_category}**, {", ".join(item.category)}  
> Authors: {", ".join(item.author)}  
> Date: {item.updated}{f" (Published @{item.published})" if item.updated != item.published else ""}  

***摘要:***  
**这是摘要**

***Abstract:***  
{item.summary}
---
"""
    return template


def generate(cate_list: list[str], tag: str):
    print(f"Querying RSS for Category: {cate_list}")
    id_list = []
    for cate in cate_list:
        rss_str = query_rss(cate)
        rss_items = parse_rss(rss_str)
        id_list += [item.link.strip("/").split("/")[-1] for item in rss_items]
    id_list = list(set(id_list))
    id_list.sort(reverse=True)
    
    print(f"Collecting detailed paper information for {len(id_list)} papers")
    atom_strs = query_atom(id_list, items_per_req=20, force=False)
    atom_items = []
    for atom_str in atom_strs:
        atom_items += parse_atom(atom_str)

    print(f"Generating markdown")
    date = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    with open(f"Feed-{date}-{tag}.md", "w") as f:
        for atom_item in atom_items:
            f.write(generate_markdown(atom_item))

if __name__ == "__main__":
    generate(ArxivCategory.SYS_CATEGORY, "SYS")
    generate(ArxivCategory.AI_CATEGORY, "AI")

"""
TODO
1. Breakline
2. Updated tag
"""