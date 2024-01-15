import datetime
import re

import pytz

_local_tz = pytz.timezone("Asia/Shanghai")
_utc_tz = pytz.timezone("UTC")


def get_local_time(raw_datetime: datetime.datetime | str) -> datetime.datetime:
    if raw_datetime is str:
        raw_datetime = datetime.datetime.fromisoformat(raw_datetime)
    return raw_datetime.astimezone(_local_tz)


def get_utc_time(raw_datetime: datetime.datetime | str) -> datetime.datetime:
    if raw_datetime is str:
        raw_datetime = datetime.datetime.fromisoformat(raw_datetime)
    return raw_datetime.astimezone(_utc_tz)

def pre_process_abstract(raw_text: str) -> str:
    lines = raw_text.splitlines()
    paragraphs = []
    assert lines[0].startswith("  ")
    for line in lines:
        if line.startswith("  "):
            paragraphs.append(line[2:])
        else:
            paragraphs[-1] += " " + line 
    return  "\n\n".join(paragraphs)\

def pre_proc_title(raw_title: str) -> str:
    return re.sub(r'\s+', ' ', raw_title)