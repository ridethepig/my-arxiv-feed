import urllib.parse
import requests

GOOGLE_TRANSLATE_URL = "https://translate.google.com"


def RL(a, b):
    t = "a"
    Yb = "+"
    d = 0
    for c in range(0, len(b) - 2, 3):
        d = ord(b[c + 2])
        d = d - 87 if d >= ord(t) else int(d)
        d = a >> d if b[c + 1] == Yb else a << d
        a = (a + d) & 4294967295 if b[c] == Yb else a ^ d
    return a


def TL(a):
    b = 406644
    b1 = 3293161072
    jd = "."
    sb = "+-a^+6"
    Zb = "+-3^+b+-f"
    e = []
    f = 0
    g = 0
    for g in range(len(a)):
        m = ord(a[g])
        if m < 128:
            e.append(m)
            f += 1
        elif m < 2048:
            e.append((m >> 6) | 192)
            e.append((m & 63) | 128)
            f += 2
        elif 55296 == (m & 64512) and g + 1 < len(a) and 56320 == (ord(a[g + 1]) & 64512):
            m = 65536 + ((m & 1023) << 10) + (ord(a[g + 1]) & 1023)
            e.append((m >> 18) | 240)
            e.append(((m >> 12) & 63) | 128)
            e.append(((m >> 6) & 63) | 128)
            e.append((m & 63) | 128)
            f += 4
            g += 1
        else:
            e.append((m >> 12) | 224)
            e.append(((m >> 6) & 63) | 128)
            e.append((m & 63) | 128)
            f += 3
    a = b
    for f in range(len(e)):
        a += e[f]
        a = RL(a, sb)
    a = RL(a, Zb)
    a ^= b1 or 0
    if a < 0:
        a = (a & 2147483647) + 2147483648
    a %= 1000000
    return str(a) + jd + str(a ^ b)


def translate(data: str):
    langfrom = "en-US"
    langto = "zh-CN"
    param = f"sl={langfrom}&tl={langto}"
    tk = TL(data)
    q = urllib.parse.quote(data)
    resp = requests.get(
        f"{GOOGLE_TRANSLATE_URL}/translate_a/single?client=gtx&{param}&hl=zh-CN&dt=at&dt=bd&dt=ex&dt=ld&dt=md&dt=qca&dt=rw&dt=rm&dt=ss&dt=t&source=bh&ssel=0&tsel=0&kc=1&tk={tk}&q={q}")
    resp_json = resp.json()
    tgt = ""
    for i in range(len(resp_json[0])):
        if not resp_json[0][i]:
            continue
        if resp_json[0][i] and resp_json[0][i][0]:
            tgt += resp_json[0][i][0]
    return tgt


if __name__ == "__main__":
    print("Test:")
    print(translate("What are you doing now?"))
