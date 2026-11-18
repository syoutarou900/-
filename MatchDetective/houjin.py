# -*- coding: utf-8 -*-
"""Client for the National Tax Agency （国税庁） corporate-number
（法人番号） Web-API Ver.4 — the name-search function.

Spec verified 2026-11-13 against the official documents:
- API overview: https://www.houjin-bangou.nta.go.jp/pc/webapi/
- Ver.4.0 request/response spec, part 6 (第六編）, section 4
  （法人名を指定して情報を取得する機能）:
  https://www.houjin-bangou.nta.go.jp/pc/webapi/images/k-web-api-kinou-ver4.pdf
- Field definitions （リソース定義書）: root <corporations> carries the
  header lastUpdateDate / count / divideNumber / divideSize; each
  <corporation> carries corporateNumber, name, furigana,
  prefectureName, cityName, streetNumber, postCode, kind, latest, ...
- The free application ID is issued via the NTA invoice site:
  https://www.invoice-kohyo.nta.go.jp/web-api/index.html
  (linked from the 法人番号 Web-API page for ID procedures).

Request: GET {API_BASE}?id={application ID}&name={法人名, UTF-8
URL-encoded}&type=12   — type 12 = XML / Unicode.
Results over 2,000 records are split: follow divideNumber up to
divideSize. This module never guesses: any transport or format problem
raises HoujinError with a kind the UI turns into a clear message.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

import core

API_BASE = "https://api.houjin-bangou.nta.go.jp/4/name"
REGISTRATION_URL = "https://www.invoice-kohyo.nta.go.jp/web-api/index.html"
API_PAGE_URL = "https://www.houjin-bangou.nta.go.jp/pc/webapi/"
# Attribution wording requested by the NTA for services using the API.
ATTRIBUTION_JA = ("このサービスは、国税庁法人番号システムのWeb-API機能を利用して"
                  "取得した情報をもとに作成しているが、サービスの内容は国税庁に"
                  "よって保証されたものではない")
MAX_DIVIDE = 10          # safety cap on split-response pages


class HoujinError(Exception):
    """kind: 'no_id' | 'network' | 'http' | 'parse'."""

    def __init__(self, kind, detail=""):
        super().__init__(kind + (": " + str(detail) if detail else ""))
        self.kind = kind
        self.detail = detail


class Corporation:
    __slots__ = ("number", "name", "furigana", "prefecture", "city",
                 "street", "postcode", "kind", "latest")

    def __init__(self, number="", name="", furigana="", prefecture="",
                 city="", street="", postcode="", kind="", latest="1"):
        self.number = number
        self.name = name
        self.furigana = furigana
        self.prefecture = prefecture
        self.city = city
        self.street = street
        self.postcode = postcode
        self.kind = kind
        self.latest = latest

    @property
    def address(self):
        return (self.prefecture + self.city + self.street).strip()

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: str(d.get(k, "")) for k in cls.__slots__})

    def __eq__(self, other):
        return isinstance(other, Corporation) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return "Corporation(%s %s)" % (self.number, self.name)


def _default_fetch(url, timeout):
    req = urllib.request.Request(
        url, headers={"User-Agent": "MatchDetective/1.0 (+houjin-bangou Web-API)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class HoujinClient:
    """Name search with a JSON file cache. `fetcher(url, timeout) ->
    bytes` is injectable so tests run entirely on fixtures."""

    def __init__(self, app_id, cache_path=None, fetcher=None, timeout=15):
        self.app_id = (app_id or "").strip()
        self.cache_path = cache_path
        self.fetcher = fetcher or _default_fetch
        self.timeout = timeout
        self._cache = {}
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as fh:
                    self._cache = json.load(fh)
            except Exception:
                self._cache = {}

    # -- request / response -------------------------------------------
    def build_url(self, name, divide=1):
        params = {"id": self.app_id, "name": name, "type": "12"}
        if divide > 1:
            params["divide"] = str(divide)
        return API_BASE + "?" + urllib.parse.urlencode(params)

    @staticmethod
    def parse_response(data):
        """bytes -> (last_update_date, [Corporation], divide_no, divide_size).
        Raises HoujinError('parse') on anything that is not the official
        <corporations> document."""
        try:
            root = ET.fromstring(data)
        except Exception as exc:
            raise HoujinError("parse", exc)
        if root.tag != "corporations":
            raise HoujinError("parse", "unexpected root: %s" % root.tag)

        def txt(parent, tag):
            el = parent.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        records = []
        for corp in root.findall("corporation"):
            records.append(Corporation(
                number=txt(corp, "corporateNumber"),
                name=txt(corp, "name"),
                furigana=txt(corp, "furigana"),
                prefecture=txt(corp, "prefectureName"),
                city=txt(corp, "cityName"),
                street=txt(corp, "streetNumber"),
                postcode=txt(corp, "postCode"),
                kind=txt(corp, "kind"),
                latest=txt(corp, "latest") or "1",
            ))
        try:
            dno = int(txt(root, "divideNumber") or "1")
            dsz = int(txt(root, "divideSize") or "1")
        except ValueError:
            dno, dsz = 1, 1
        return txt(root, "lastUpdateDate"), records, dno, dsz

    def _fetch_page(self, name, divide):
        url = self.build_url(name, divide)
        try:
            data = self.fetcher(url, self.timeout)
        except urllib.error.HTTPError as exc:
            raise HoujinError("http", exc.code)
        except HoujinError:
            raise
        except Exception as exc:            # URLError, timeout, socket...
            raise HoujinError("network", exc)
        return self.parse_response(data)

    # -- cache ----------------------------------------------------------
    def _save_cache(self):
        if not self.cache_path:
            return
        folder = os.path.dirname(self.cache_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as fh:
            json.dump(self._cache, fh, ensure_ascii=False)

    # -- public ---------------------------------------------------------
    def search_by_name(self, name, use_cache=True):
        """-> {"records": [Corporation], "last_update": str,
        "fetched": "YYYY-MM-DD", "from_cache": bool}"""
        if not self.app_id:
            raise HoujinError("no_id")
        name = str(name).strip()
        if not name:
            raise HoujinError("parse", "empty name")
        if use_cache and name in self._cache:
            hit = self._cache[name]
            return {"records": [Corporation.from_dict(r)
                                for r in hit["records"]],
                    "last_update": hit["last_update"],
                    "fetched": hit["fetched"], "from_cache": True}
        last_update, records, _dno, dsz = self._fetch_page(name, 1)
        divide = 2
        while dsz > 1 and divide <= min(dsz, MAX_DIVIDE):
            _lu, more, _dn, _ds = self._fetch_page(name, divide)
            records.extend(more)
            divide += 1
        entry = {"records": [r.to_dict() for r in records],
                 "last_update": last_update,
                 "fetched": date.today().isoformat()}
        self._cache[name] = entry
        self._save_cache()
        return {"records": records, "last_update": last_update,
                "fetched": entry["fetched"], "from_cache": False}


def registry_matches(records, name_x):
    """The distinct current corporations whose registered 商号 equals
    name_x after the app's deterministic normalization. This — never a
    similarity score — is what 'the registry returns for X' means here."""
    nx = core.normalize_company(name_x)
    if not nx:
        return []
    out, seen = [], set()
    for r in records:
        if r.latest == "0":
            continue
        if core.normalize_company(r.name) == nx and r.number not in seen:
            seen.add(r.number)
            out.append(r)
    return out


def evaluate(records, name_x, name_y):
    """The ONLY automatic identity from the registry.

    name_x: the non-kana company name as displayed; name_y: the variant
    on the other side. Returns (status, payload):
      ("auto", Corporation)  — exactly one corporation is registered
        under name_x, and name_y is kana-only and its kana-folded form
        equals that corporation's registered フリガナ (kana-folded).
      ("multi", [Corporation...]) — several corporations share name_x;
        a human must pick (the evidence list).
      ("none", [Corporation...]) — no provable identity.
    """
    matches = registry_matches(records, name_x)
    if len(matches) > 1:
        return "multi", matches
    if len(matches) == 0:
        return "none", matches
    rec = matches[0]
    if not core.is_kana_only(name_y) or not rec.furigana:
        return "none", matches
    # kana_core strips legal forms AND their kana readings on both
    # sides, so 株式会社タナカデンキ / タナカデンキ（株） / furigana
    # カブシキガイシャタナカデンキ all reduce to the same key.
    if core.kana_core(name_y) == core.kana_core(rec.furigana):
        return "auto", rec
    return "none", matches
