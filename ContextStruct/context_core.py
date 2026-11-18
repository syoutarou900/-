# -*- coding: utf-8 -*-
import re, json, os, sys, shutil, csv, io
from dataclasses import dataclass, field as dc_field, asdict

MONTHS = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
"january":1,"february":2,"march":3,"april":4,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}

def parse_number(text):
    if text is None: return ""
    s = str(text)
    # find first number-like token
    m = re.search(r'-?\d[\d,]*\.?\d*', s)
    if not m: return ""
    v = m.group(0).replace(",","")
    # normalize: if float with trailing zeros keep simple
    try:
        if "." in v:
            f=float(v); return ('%f'%f).rstrip('0').rstrip('.') if '.' in ('%f'%f) else v
        return str(int(v))
    except: return v

def parse_date(text):
    if not text: return ""
    s=str(text).strip()
    # YYYY/MM/DD or YYYY-MM-DD or YYYY.MM.DD
    m=re.search(r'(20\d{2}|19\d{2})[/\-\.](\d{1,2})[/\-\.](\d{1,2})', s)
    if m: return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # YYYY年M月D日
    m=re.search(r'(20\d{2}|19\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', s)
    if m: return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 12 Nov 2026
    m=re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2}|19\d{2})', s)
    if m and m.group(2).lower()[:3] in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    # Nov 12, 2026
    m=re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2}|19\d{2})', s)
    if m and m.group(1).lower() in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return ""

def format_value(raw, ftype):
    if raw is None: return ""
    raw=str(raw).strip()
    if ftype in ("number","amount"):
        return parse_number(raw)
    if ftype=="date":
        return parse_date(raw) or ""
    return raw.strip(" :：\t")

@dataclass
class FieldDef:
    display_name: str
    target_column: str
    keywords: str  # comma separated string
    field_type: str = "text"
    required: bool = False
    def keyword_list(self):
        return [k.strip() for k in re.split(r'[,、]', self.keywords) if k.strip()]

@dataclass
class Profile:
    name: str
    fields: list = dc_field(default_factory=list)
    def to_dict(self): return {"name":self.name,"fields":[asdict(f) for f in self.fields]}
    @staticmethod
    def from_dict(d):
        return Profile(name=d.get("name",""), fields=[FieldDef(**{k:f.get(k, "" if k!="required" else False) for k in ["display_name","target_column","keywords","field_type","required"]}) for f in d.get("fields",[])])

def preset_profiles():
    profiles=[]
    profiles.append(Profile("納品書 Delivery Note", [
        FieldDef("納品書番号","納品書番号","納品書番号,納品No,Delivery No,Delivery Number","text",True),
        FieldDef("納品日","納品日","納品日,納品年月日,Delivery Date","date",True),
        FieldDef("取引先","取引先","取引先,納入先,宛先,Customer","text",False),
        FieldDef("商品名","商品名","商品名,品名,品目,Product Name,Product","text",False),
        FieldDef("数量","数量","数量,個数,Qty,Quantity","number",False),
        FieldDef("単価","単価","単価,Unit Price","amount",False),
        FieldDef("卸値","卸値","卸値,卸価格,仕入価格,Wholesale Price,Wholesale","amount",False),
        FieldDef("売価","売価","売価,販売価格,小売価格,Retail Price,Retail,Selling Price","amount",False),
        FieldDef("合計","合計","合計金額,合計,Total Amount,Total","amount",False),
    ]))
    profiles.append(Profile("請求書 Invoice", [
        FieldDef("請求書番号","請求書番号","請求書番号,Invoice No,Invoice Number","text",True),
        FieldDef("請求日","請求日","請求日,発行日,Invoice Date,Issue Date","date",True),
        FieldDef("請求先","請求先","請求先,宛先,Bill To,Customer","text",False),
        FieldDef("商品名","商品名","商品名,品名,Product","text",False),
        FieldDef("数量","数量","数量,Qty,Quantity","number",False),
        FieldDef("小計","小計","小計,Subtotal","amount",False),
        FieldDef("消費税","消費税","消費税,税額,Tax","amount",False),
        FieldDef("請求金額","請求金額","請求金額,ご請求金額,合計金額,Amount Due,Total","amount",True),
    ]))
    profiles.append(Profile("WEBカタログ商品 Product Catalog", [
        FieldDef("商品名","商品名","商品名,品名,Product Name,Product","text",True),
        FieldDef("商品コード","商品コード","商品コード,型番,SKU,Product Code,Code","text",False),
        FieldDef("数量","数量","数量,Qty,Quantity","number",False),
        FieldDef("卸値","卸値","卸値,卸価格,仕入価格,Wholesale Price,Wholesale","amount",False),
        FieldDef("売価","売価","売価,販売価格,小売価格,Retail Price,Retail,Selling Price","amount",False),
        FieldDef("在庫数","在庫数","在庫数,在庫,Stock","number",False),
    ]))
    profiles.append(Profile("汎用 General", [
        FieldDef("日付","日付","日付,年月日,Date","date",False),
        FieldDef("名称","名称","名称,名前,Name,Title","text",False),
        FieldDef("数量","数量","数量,個数,Qty,Quantity","number",False),
        FieldDef("金額","金額","金額,価格,Amount,Price","amount",False),
        FieldDef("備考","備考","備考,メモ,Notes,Remarks","text",False),
    ]))
    return profiles

@dataclass
class FieldResult:
    value: str = ""
    confidence: int = 0
    reason: str = ""
    snippet: str = ""

def confidence_category(conf):
    if conf>=80: return "green"
    if conf>=50: return "yellow"
    return "red"
# alias for tests expecting color
def confidence_color_category(conf): return confidence_category(conf)

def _extract_from_remainder(remainder, ftype):
    remainder=remainder.strip(" \t:：-")
    if not remainder: return ""
    if ftype in ("number","amount"):
        return parse_number(remainder)
    if ftype=="date":
        return parse_date(remainder)
    # text: take remainder, strip trailing price-like? keep whole, cut at double space
    # If remainder contains another known separator? keep first segment
    return remainder.strip()

def extract_field(text_lines, field_def):
    kws = sorted(field_def.keyword_list(), key=len, reverse=True)
    candidates=[]  # (value, conf, reason, snippet)
    for idx, line in enumerate(text_lines):
        stripped=line.strip()
        if not stripped: continue
        for kw in kws:
            if kw.lower() in stripped.lower():
                # find position (case-insensitive)
                pos = stripped.lower().find(kw.lower())
                remainder = stripped[pos+len(kw):].strip()
                # remainder may start with colon etc
                val = _extract_from_remainder(remainder, field_def.field_type)
                if val:
                    conf=95 if field_def.field_type in ("number","amount","date") else 90
                    candidates.append((val, conf, "reason_exact + reason_type_ok", stripped))
                else:
                    # next line
                    if idx+1 < len(text_lines):
                        nxt=text_lines[idx+1].strip()
                        val2=_extract_from_remainder(nxt, field_def.field_type)
                        if val2:
                            candidates.append((val2, 75, "reason_next", stripped+" / "+nxt))
                break  # only longest kw per line
    if not candidates:
        return FieldResult("",0,"not_found","")
    # deduplicate values
    uniq={}
    for v,c,r,s in candidates:
        if v not in uniq or c>uniq[v][1]: uniq[v]=(v,c,r,s)
    best = max(uniq.values(), key=lambda x: x[1])
    conf=best[1]; reason=best[2]
    if len(uniq)>1:
        conf=max(0, conf-15); reason=reason+" + reason_multi"
    return FieldResult(best[0], conf, reason, best[3])

def detect_line_items(lines, profile):
    # pattern: name + qty + price at end, at least 2 numbers
    items=[]
    # identify target names
    name_target=None; qty_target=None; price_target=None
    for f in profile.fields:
        dn=f.display_name; tc=f.target_column
        if any(k in dn for k in ["商品","品名","名称","Product"]): name_target=tc
        if "数量" in dn or "Qty" in dn: qty_target=tc
        if "単価" in dn: price_target=tc
    if not name_target: return []
    pat=re.compile(r'^(.+?)[\s\t]+(\d[\d,]*)\s*(?:個|pcs|件)?[\s\t]+[¥￥]?\s*(\d[\d,]*)\s*(?:円)?\s*$')
    for line in lines:
        s=line.strip()
        if any(x in s for x in ["合計","小計","卸値","売価","消費税","請求金額"]): continue
        if ":" in s or "：" in s or ":" in s: continue
        m=pat.match(s)
        if m:
            items.append({name_target:m.group(1).strip(), qty_target:parse_number(m.group(2)) if qty_target else "", price_target:parse_number(m.group(3)) if price_target else ""})
    if len(items)>=2:
        # filter None keys
        cleaned=[]
        for it in items:
            cleaned.append({k:v for k,v in it.items() if k})
        return cleaned
    return []

def extract_document(text, profile):
    lines=text.splitlines()
    base={}
    for f in profile.fields:
        base[f.target_column]=extract_field(lines, f)
    items=detect_line_items(lines, profile)
    rows=[]
    if items:
        for it in items:
            row={}
            for f in profile.fields:
                tc=f.target_column
                if tc in it:
                    row[tc]=FieldResult(it[tc], 80, "reason_table", "")
                else:
                    # single-doc fields fill every row: copy base
                    row[tc]=FieldResult(base[tc].value, base[tc].confidence, base[tc].reason, base[tc].snippet)
            rows.append(row)
    else:
        rows.append(base)
    return rows

def rows_to_tsv(rows, profile, include_header=True):
    cols=[f.target_column for f in profile.fields]
    out=[]
    if include_header: out.append("\t".join(cols))
    for r in rows:
        out.append("\t".join((r[c].value if isinstance(r.get(c), FieldResult) else str(r.get(c,""))) for c in cols))
    return "\n".join(out)

def rows_to_dicts(rows, profile):
    cols=[f.target_column for f in profile.fields]
    return [{c:(r[c].value if isinstance(r.get(c), FieldResult) else str(r.get(c,""))) for c in cols} for r in rows]

def get_app_dir():
    if sys.platform.startswith("win"):
        base=os.environ.get("APPDATA") or os.path.expanduser("~")
        d=os.path.join(base,"ContextStruct")
    elif sys.platform=="darwin":
        # macOS standard per-app data location (~/Library/Application Support).
        # Only this branch is new; the Windows path above is unchanged.
        d=os.path.join(os.path.expanduser("~"),"Library","Application Support","ContextStruct")
    else:
        d=os.path.join(os.path.expanduser("~"),".contextstruct")
    os.makedirs(d, exist_ok=True)
    return d

def save_profile(profile, path=None):
    if path is None:
        safe=re.sub(r'[^\w\- ]','_',profile.name)
        path=os.path.join(get_app_dir(), safe+".json")
    with open(path,"w",encoding="utf-8") as f: json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
    return path

def load_profile(path):
    with open(path,encoding="utf-8") as f: data=json.load(f)
    return Profile.from_dict(data)

# Settings
def settings_path(): return os.path.join(get_app_dir(),"settings.json")
def load_settings():
    p=settings_path()
    if os.path.exists(p):
        try:
            with open(p,encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"language":"ja","ocr_lang":"jpn+eng","hotkey":"Ctrl+Shift+S","vlm_endpoint":"","vlm_key":"","vlm_model":"","default_output":"tsv","ocr_dpi":200,"extract_mode":"auto","vlm_use_api":False,
    # --- v2 additions ---
    "vlm_model_size":"3b","master_csv":"","optional_ocr":False,
    "learning_enabled":True,
    "watch_enabled":False,"watch_folder":"","auto_output_path":"","auto_done_folder":"","auto_review_folder":"","auto_threshold":90}
def save_settings(s):
    with open(settings_path(),"w",encoding="utf-8") as f: json.dump(s,f,ensure_ascii=False,indent=2)

# --- Text extraction ---
# Homebrew install locations checked explicitly on macOS only: apps launched
# from Finder/.app often run with a minimal PATH that lacks these directories,
# so shutil.which() alone can miss a working Homebrew Tesseract there.
HOMEBREW_TESSERACT_CANDIDATES = ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract")

def tesseract_path():
    """Resolve the Tesseract executable. On Windows (and everywhere else) this
    is exactly shutil.which('tesseract') as before; on macOS the Homebrew
    locations are checked as a fallback, in that order."""
    p = shutil.which("tesseract")
    if p: return p
    if sys.platform == "darwin":
        for cand in HOMEBREW_TESSERACT_CANDIDATES:
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None

def ocr_available():
    return tesseract_path() is not None

def ocr_image(pil_image, lang_hint="jpn+eng"):
    if not ocr_available(): return None
    try:
        import pytesseract
        if sys.platform == "darwin":
            # Point pytesseract at the resolved binary (needed when it was
            # found via the Homebrew fallback and is not on PATH).
            _tp = tesseract_path()
            if _tp: pytesseract.pytesseract.tesseract_cmd = _tp
        # pytesseract lang names: jpn+eng is tesseract format; pass as is if possible, fallback eng
        try: return pytesseract.image_to_string(pil_image, lang=lang_hint)
        except: return pytesseract.image_to_string(pil_image)
    except Exception:
        return None

def extract_text_from_pdf(path):
    """Return (text, used_ocr_attempted)"""
    try:
        import fitz
    except ImportError:
        try: import pymupdf as fitz
        except: return "", False
    doc=fitz.open(path)
    texts=[]; ocr_attempted=False
    for page in doc:
        t=page.get_text().strip()
        if t:
            texts.append(t)
        else:
            # scanned: render to pixmap then OCR
            ocr_attempted=True
            try:
                pix=page.get_pixmap(dpi=int(load_settings().get("ocr_dpi",200) or 200))
                from PIL import Image
                import io as _io
                img=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
                o=ocr_image(img, load_settings().get("ocr_lang","jpn+eng"))
                if o: texts.append(o)
            except Exception:
                pass
    doc.close()
    return "\n".join(texts), ocr_attempted

def extract_text_from_image_file(path):
    from PIL import Image
    img=Image.open(path)
    o=ocr_image(img, load_settings().get("ocr_lang","jpn+eng"))
    return o  # may be None

def call_vlm(image_path, profile, settings):
    """Optional OpenAI-compatible vision call. Returns dict target->value or None if not configured."""
    ep=(settings.get("vlm_endpoint") or "").strip(); key=(settings.get("vlm_key") or "").strip(); model=(settings.get("vlm_model") or "").strip()
    if not ep or not model: return None
    import urllib.request, base64, mimetypes
    with open(image_path,"rb") as f: b64=base64.b64encode(f.read()).decode()
    mime=mimetypes.guess_type(image_path)[0] or "image/png"
    fields_desc=", ".join([f"{f.target_column} (keywords: {f.keywords}, type:{f.field_type})" for f in profile.fields])
    prompt=f"Extract values as JSON object with keys exactly these target columns: {fields_desc}. Return only JSON."
    payload={"model":model,"messages":[{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}}]}]}
    url=ep.rstrip("/")
    if not url.endswith("/chat/completions"): url=url+"/chat/completions"
    req=urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type":"application/json", **({"Authorization":f"Bearer {key}"} if key else {})})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data=json.loads(resp.read().decode("utf-8"))
    content=data["choices"][0]["message"]["content"]
    m=re.search(r'\{.*\}', content, re.S)
    if m: return json.loads(m.group(0))
    return None
