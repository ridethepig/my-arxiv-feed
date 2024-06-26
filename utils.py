import datetime
import logging
import pickle
import re

import pytz

_local_tz = pytz.timezone("Asia/Shanghai")
_utc_tz = pytz.timezone("UTC")
_arxiv_tz = pytz.timezone("EST")


def parse_time(time_str: str) -> datetime.datetime:
    assert isinstance(time_str, str)
    try:
        return datetime.datetime.fromisoformat(time_str)
    except:
        pass
    return datetime.datetime.strptime(time_str, "%a, %d %b %Y %H:%M:%S %z")


def get_local_time(raw_datetime: datetime.datetime | str) -> datetime.datetime:
    if isinstance(raw_datetime, str):
        raw_datetime = parse_time(raw_datetime)
    return raw_datetime.astimezone(_local_tz)


def get_utc_time(raw_datetime: datetime.datetime | str) -> datetime.datetime:
    if isinstance(raw_datetime, str):
        raw_datetime = parse_time(raw_datetime)
    return raw_datetime.astimezone(_utc_tz)


def get_arxiv_time(raw_datetime: datetime.datetime | str) -> datetime.datetime:
    if isinstance(raw_datetime, str):
        raw_datetime = parse_time(raw_datetime)
    return raw_datetime.astimezone(_arxiv_tz)


def pre_process_latex(raw_text: str) -> str:
    text = raw_text
    text = re.sub(r"\$\s*\\times\s*\$", "times", text)
    # a common pattern in arXiv abs: ... outperforms the SOTA by 2.56 $\times$
    if re.match(re.compile(r"\$.*\$"), text) is not None:
        logger.warn("Unsupported math notation!")
    else:
        logger.error(re.match(re.compile(r"\$.*\$"), text))
    text = re.sub(r"\\([&%\$#_\{\}])", r"\1", text)
    # The following 10 characters have special meanings in (La)TeX:
    # & % $ # _ { } ~ ^ \
    # ==>
    # \& \% \$ \# \_ \{ \} \textasciitilde \textasciicircum \textbackslash
    return text


def pre_process_abstract(raw_text: str) -> str:
    lines = raw_text.splitlines()
    paragraphs = []
    assert lines[0].startswith("  ")
    for line in lines:
        if line.startswith("  "):
            paragraphs.append(line[2:])
        else:
            paragraphs[-1] += " " + line
    text = "\n\n".join(paragraphs)
    text = pre_process_latex(text)
    return text


def pre_proc_title(raw_title: str) -> str:
    return re.sub(r"\s+", " ", raw_title)


def pkl_load(obj_path):
    with open(obj_path, "rb") as pkl_file:
        obj = pickle.load(pkl_file)
    return obj


def pkl_dump(obj, obj_path):
    with open(obj_path, "wb") as pkl_file:
        pickle.dump(obj, pkl_file)


logger = logging.getLogger("arxiv-feed")


def logger_init(level_print: int, level_file: int | None = None):
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)d [%(levelname)s] %(message)s", datefmt="%y%m%d.%H:%M:%S"
    )
    short_formatter = logging.Formatter(
        "[%(levelname)s] %(message)s", datefmt="%y%m%d.%H:%M:%S"
    )
    # file handler
    if level_file is not None:
        fh = logging.FileHandler("arxiv-feed.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    # console handler
    ch = logging.StreamHandler()
    ch.setLevel(level_print)
    ch.setFormatter(short_formatter)
    logger.addHandler(ch)
