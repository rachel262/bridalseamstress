#!/usr/bin/env python3
"""Build the static bridalseamstress.com.au site from the master list export.

Usage: python3 build.py master.json out_dir [--preview]
--preview writes links ending in index.html so the pages work as plain files.
"""
import json, re, sys, os, html, unicodedata, collections, shutil
from urllib.parse import urlencode

SRC, OUT = sys.argv[1], sys.argv[2]
PREVIEW = '--preview' in sys.argv
SITE = 'https://bridalseamstress.com.au'
CHECKED = 'Nov 2026'
import datetime
TODAY = datetime.date.today().isoformat()

STATE_NAMES = {'QLD': 'Queensland', 'NSW': 'New South Wales', 'VIC': 'Victoria', 'SA': 'South Australia',
               'WA': 'Western Australia', 'ACT': 'Australian Capital Territory', 'TAS': 'Tasmania', 'NT': 'Northern Territory'}
STATE_ORDER = ['QLD', 'NSW', 'ACT', 'VIC', 'TAS', 'SA', 'WA', 'NT']
TAGS = ['Wedding dress alterations', 'Custom gowns', 'Bustles', 'Rush jobs', 'Restyling', 'Corset backs', 'Bridesmaids', 'Mother of the bride', 'Formal gowns', 'Home visits']
# service name (sheet column X or data/enrichment.csv) -> city page filter
SERVICE_TAGS = {'bustles': 'Bustles', 'rush jobs': 'Rush jobs', 'custom gowns': 'Custom gowns', 'restyling and redesign': 'Restyling',
    'corset back conversion': 'Corset backs', 'bridesmaid dresses': 'Bridesmaids', 'mother of the bride': 'Mother of the bride',
    'formal and evening wear': 'Formal gowns', 'mobile or home visits': 'Home visits'}

e = lambda s: html.escape(str(s), quote=True)

# bride shopping page (affiliate links); skipped when the data file is missing, e.g. the US build
CARE_FILE = os.path.join(os.path.dirname(os.path.abspath(SRC)), 'care_picks.json')
CARE = json.load(open(CARE_FILE, encoding='utf-8')) if os.path.exists(CARE_FILE) else None
CARE_PATH = 'wedding-dress-care/'


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s.lower()).strip('-')
    return s[:70].strip('-') or 'listing'


def fmt_phone(p):
    p = p.strip()
    if p.startswith('+61 '):
        rest = p[4:]
        if rest.startswith(('4', '1')):
            return rest if rest.startswith('1') else '0' + rest
        return '(0' + rest[0] + ') ' + rest[2:]
    return p


def tags_for(r):
    t = (r['notes'] + ' ' + r['subtypes'] + ' ' + r.get('services', '')).lower()
    bt = r['business_type']
    out = []
    if bt != 'maker' and ('alter' in t or bt in ('alterations', 'both', 'shop-with-alterations')):
        out.append('Wedding dress alterations')
    if bt in ('maker', 'both') or re.search(r'custom|bespoke|made to|hand ?craft|makes|couture|designer', r['notes'].lower()):
        out.append('Custom gowns')
    if 'bustle' in t:
        out.append('Bustles')
    if 'bridesmaid' in t:
        out.append('Bridesmaids')
    if re.search(r'formal|ball gown|evening', t):
        out.append('Formal gowns')
    for sv in r.get('_services', []):
        tg = SERVICE_TAGS.get(sv.lower())
        if tg and tg not in out:
            out.append(tg)
    if not out:
        out.append('Wedding dress alterations')
    return [t for t in TAGS if t in out]


def blurb_for(r, tags):
    if r['business_type'] == 'shop-with-alterations':
        return 'Bridal shop with alterations done in house.'
    alt, make = 'Wedding dress alterations' in tags, 'Custom gowns' in tags
    if alt and make:
        return 'Alters wedding dresses and makes gowns to order.'
    if make:
        return 'Makes bridal gowns to order.'
    return 'Alters wedding dresses.'


# ---------- load ----------
d = json.load(open(SRC))['values']
h = d[0]
rows = [dict(zip(h, r + [''] * (len(h) - len(r)))) for r in d[1:]]
live = [r for r in rows if r['checked_bridal (Y/N)'] == 'Y' and r['business_status'] != 'CLOSED_TEMPORARILY']

# website crawl results (data/enrichment.csv, keyed by place_id): services used when the sheet has none
ENRICH = {}
_ep = os.path.join(os.path.dirname(os.path.abspath(SRC)), 'enrichment.csv')
if os.path.exists(_ep):
    import csv
    ENRICH = {x['place_id']: x for x in csv.DictReader(open(_ep, encoding='utf-8'))}
for r in live:
    own = [x.strip(' -•').strip() for x in re.split(r'\n|;', r.get('services', '')) if x.strip(' -•').strip()]
    crawled = [x.strip() for x in ENRICH.get(r['place_id'], {}).get('services', '').split('\n') if x.strip()]
    r['_own_services'] = own
    r['_services'] = own or crawled  # the owner's own list wins over the website crawl

cities = collections.OrderedDict()
for r in live:
    cname, st = r['search_city'].rsplit(' ', 1)
    key = slugify(cname)
    c = cities.setdefault(key, {'name': cname, 'state': st, 'slug': key, 'listings': []})
    c['listings'].append(r)

listings = []
for c in cities.values():
    used = set()
    for r in c['listings']:
        s = slugify(r['name'])
        if s in used:
            s = slugify(r['name'] + ' ' + r['city'])
        n = 2
        base = s
        while s in used:
            s = f'{base}-{n}'; n += 1
        used.add(s)
        tags = tags_for(r)
        L = {
            'name': r['name'].strip(), 'slug': s, 'city': c, 'suburb': r['city'] or c['name'], 'state': r['state'] or c['state'],
            'phone': fmt_phone(r['phone']) if r['phone'] else '', 'tel': re.sub(r'[^+0-9]', '', r['phone']),
            'website': r['website'].strip(), 'maps': r['location_link'], 'rating': r['rating'], 'reviews': r['reviews'],
            'tags': tags, 'blurb': blurb_for(r, tags), 'place_id': r['place_id'], 'email': r['email'], 'serves': r.get('also_serves', '').strip(),
            'lead': r.get('lead_time', '').strip(),
            'photos': [x.strip() for x in re.split(r'[\n;,]', r.get('photos', '')) if x.strip()][:6 if r.get('featured', '').strip() else 3],
            'services': r['_own_services'] or r['_services'],
            'verified': r.get('verified', '').strip(), 'featured': bool(r.get('featured', '').strip()),
        }
        listings.append(L)
    # order: featured (badge on their own site), then verified by owner, then most reviewed
    c['items'] = sorted([L for L in listings if L['city'] is c],
                        key=lambda L: (not L['featured'], not L['verified'], -int(float(L['reviews'] or 0))))


# ---------- links ----------
def href(path):
    """path like '' or 'brisbane/' or 'brisbane/x/'; returns root-relative (live) or relative (preview)."""
    if PREVIEW:
        return path + 'index.html' if path.endswith('/') or path == '' else path
    return '/' + path


def rel(depth, path):
    if PREVIEW:
        return '../' * depth + href(path)
    return href(path)


# ---------- layout ----------
CSS = """
:root{--ink:#1E2235;--ink2:#3A3F55;--mute:#5A5E70;--line:#E7E2E4;--blush:#F7EEF0;--rose:#9C3F55;--rose-d:#7A2E41;--sage:#EEF2F0;--sage-ink:#2F4A40;--soft:#FAFAFB}
*{box-sizing:border-box}
body{margin:0;background:#fff;font-family:'Figtree',system-ui,sans-serif;color:var(--ink);font-size:16px;line-height:1.5}
a{color:var(--rose)}a:hover{color:var(--rose-d)}
.wrap{max-width:1180px;margin:0 auto;padding-left:24px;padding-right:24px}
.serif{font-family:'Cormorant Garamond',Georgia,serif;font-weight:600}
header.top{border-bottom:1px solid var(--line)}
header.top .wrap{padding-top:18px;padding-bottom:18px;display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink)}
.brand span{font-family:'Cormorant Garamond',Georgia,serif;font-size:26px;font-weight:600}
nav.main{display:flex;flex-wrap:wrap;gap:24px;align-items:center;font-size:15px}
nav.main a{color:var(--ink);text-decoration:none}
@media(max-width:480px){nav.main{gap:12px;font-size:14px}nav.main .btn{font-size:13px;padding:8px 12px;min-height:40px}}
nav.main a[aria-current]:not(.btn){text-decoration:underline;text-decoration-color:var(--rose);text-decoration-thickness:2px;text-underline-offset:6px;font-weight:600}
.btn{display:inline-block;font:inherit;font-size:15px;font-weight:500;padding:11px 18px;border-radius:999px;text-decoration:none;min-height:44px;line-height:22px;cursor:pointer}
.btn-dark{background:var(--ink);color:#fff!important;border:1px solid var(--ink)}
.btn-line{border:1px solid var(--ink);color:var(--ink)!important;background:#fff}
.btn-rose{background:var(--rose);color:#fff!important;border:0;font-weight:600}
.btn-blush{background:var(--blush);color:var(--ink)!important;font-weight:600}
.hero{background:var(--blush)}
.hero .wrap{padding-top:44px;padding-bottom:36px;display:flex;flex-direction:column;gap:14px}
.hero .wrap.hhero{display:grid;grid-template-columns:1fr;gap:28px;align-items:center}
.htext{display:flex;flex-direction:column;gap:14px}
.himg{margin:0}
.himg img{display:block;width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;object-position:50% 8%;border-radius:14px}
.himg figcaption{font-size:12px;color:var(--mute);margin-top:6px}
@media(min-width:860px){.hero .wrap.hhero{grid-template-columns:1.25fr 1fr;gap:48px}.himg img{aspect-ratio:3/4;max-height:520px}}
.crumbs{margin:0;font-size:14px;color:var(--mute)}
.crumbs a{color:var(--mute)}
h1.big{margin:0;font-family:'Cormorant Garamond',Georgia,serif;font-weight:600;font-size:52px;line-height:1.05;text-wrap:balance}
.lede{margin:0;max-width:640px;font-size:18px;line-height:1.55;color:var(--ink2)}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px}
.chip{font:inherit;font-size:14px;padding:10px 16px;border-radius:999px;border:1px solid #C9BFC3;background:#fff;color:var(--ink);min-height:44px;cursor:pointer}
.chip[aria-pressed=true]{border-color:var(--ink);background:var(--ink);color:#fff}
.cols{padding-top:32px;padding-bottom:56px;display:flex;flex-wrap:wrap;gap:32px;align-items:flex-start}
.colmain{flex:999 1 560px;min-width:0;display:flex;flex-direction:column;gap:16px}
.colside{flex:1 1 300px;min-width:260px;display:flex;flex-direction:column;gap:16px}
.card{border:1px solid var(--line);border-radius:14px;padding:22px 24px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;justify-content:space-between;background:#fff}
.card .info{flex:1 1 380px;min-width:0;display:flex;flex-direction:column;gap:8px}
.card h2{margin:0;font-size:21px;font-weight:600}
.card h2 a{color:var(--ink);text-decoration:none}
.meta{margin:0;font-size:15px;color:var(--mute)}
.num{font-variant-numeric:tabular-nums}
.tags{display:flex;flex-wrap:wrap;gap:8px}
.tag{font-size:13px;padding:5px 10px;border-radius:6px;background:var(--sage);color:var(--sage-ink)}
.tag.grey{background:#F4F4F6;color:var(--mute)}
.badge{align-self:flex-start;font-size:12px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;color:var(--rose);background:var(--blush);padding:4px 10px;border-radius:999px}
.check{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--sage-ink)}
.ver{display:inline-flex;gap:6px;align-items:center;font-size:13px;font-weight:600;color:var(--rose-d);background:var(--blush);border:1px solid #E6CFD5;border-radius:6px;padding:5px 10px}
.feat{display:inline-block;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#fff;background:var(--rose);border-radius:4px;padding:3px 8px;margin-bottom:6px}
.card .act{display:flex;flex-direction:column;gap:10px;align-items:flex-end}
.panel{border-radius:14px;border:1px solid var(--line);padding:24px;display:flex;flex-direction:column;gap:10px}
.panel.dark{background:var(--ink);color:#fff;border:0;gap:12px}
.panel.dark p{color:#D9DBE5}
.panel h3{margin:0;font-size:17px;font-weight:600}
.panel.dark h3{font-family:'Cormorant Garamond',Georgia,serif;font-size:26px}
.panel p{margin:0;font-size:15px;line-height:1.5}
.panel ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:8px;font-size:15px;line-height:1.45;color:var(--ink2)}
.soft{background:var(--soft)}
form.claim{display:flex;flex-direction:column;gap:12px}
form.claim label{display:flex;flex-direction:column;gap:6px;font-size:14px;font-weight:500}
form.claim input,form.claim textarea,form.claim select{font:inherit;font-size:15px;padding:11px 12px;border:1px solid #C9BFC3;border-radius:8px;background:#fff;color:var(--ink)}
form.claim .hp{position:absolute;left:-9999px}
.photos{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.photos div{aspect-ratio:4/5;border-radius:12px;background:var(--blush);border:1px dashed #D8C3C9;display:flex;align-items:center;justify-content:center;text-align:center;padding:12px;font-size:13px;color:#7A6970}
section.blk{display:flex;flex-direction:column;gap:10px}
section.blk h2{margin:0;font-size:20px;font-weight:600}
.statelist{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}
.statelist .panel a{text-decoration:none}
.prose{max-width:720px;display:flex;flex-direction:column;gap:14px;font-size:17px;color:var(--ink2)}
.prose h2{margin:16px 0 0;font-size:22px;color:var(--ink)}
.prose p{margin:0}
.prose h3{margin:8px 0 0;font-size:18px;color:var(--ink)}
.prose ul{margin:0;padding-left:22px}
.prose hr{border:0;border-top:1px solid var(--line);margin:12px 0}
.blog .bimg{margin:8px 0}.blog .bimg img{display:block;width:100%;max-width:520px;height:auto;border-radius:12px}
.blog .bimg figcaption{font-size:13px;color:var(--mute);margin-top:6px}
.tblwrap{overflow-x:auto}.prose table{border-collapse:collapse;width:100%;font-size:15px}
.prose th,.prose td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.prose th{color:var(--ink);font-weight:600;background:var(--soft)}
.bgrid{display:grid;grid-template-columns:1fr;gap:20px}@media(min-width:760px){.bgrid{grid-template-columns:1fr 1fr}}
.bcard{display:flex;flex-direction:column;gap:10px;text-decoration:none;color:var(--ink)}.bcard img{width:100%;aspect-ratio:4/3;object-fit:cover;object-position:50% 20%;border-radius:10px}
footer.bot{border-top:1px solid var(--line);background:var(--soft)}
footer.bot .wrap{padding-top:28px;padding-bottom:28px;display:flex;flex-wrap:wrap;gap:16px;justify-content:space-between;font-size:14px;color:var(--mute)}
[hidden]{display:none!important}
.owner{border-top:1px solid var(--line);padding-top:14px;display:flex;flex-direction:column;gap:8px;font-size:14px;color:var(--mute)}.owner p{margin:0}.btn-sm{align-self:flex-start;font-size:14px;padding:8px 14px;min-height:0}
.intro{max-width:760px;display:flex;flex-direction:column;gap:10px;margin:4px 0 14px;color:var(--ink2)}.intro p{margin:0}
.faq{display:flex;flex-direction:column;gap:10px;margin-top:28px}.faq h2{margin:0 0 4px;font-size:30px}
.faq details{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fff}.faq summary{font-weight:600;cursor:pointer}.faq details p{margin:10px 0 0;color:var(--ink2)}
@media (max-width:600px){h1.big{font-size:38px}.card .act{align-items:flex-start}.photos{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""

LOGO = '<svg width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="#9C3F55" stroke-width="1.6" aria-hidden="true"><circle cx="14" cy="14" r="12"/><path d="M8 20 L20 8"/><circle cx="19" cy="9" r="1.6"/></svg>'
VTICK = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7.5" fill="#9C3F55"/><path d="M4.6 8.3l2.2 2.2 4.6-4.8" fill="none" stroke="#fff" stroke-width="1.8"/></svg>'
TICK = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#2F4A40" stroke-width="1.8" aria-hidden="true"><path d="M3 8.5l3 3 7-7"/></svg>'


def page(depth, path, title, desc, body, jsonld=None):
    r = lambda p: rel(depth, p)
    canon = SITE + '/' + path
    if isinstance(jsonld, list):
        jsonld = {'@context': 'https://schema.org', '@graph': [{k: v for k, v in x.items() if k != '@context'} for x in jsonld]}
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ''
    return f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-LSJY554PMM"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-LSJY554PMM');</script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canon)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canon)}">
<link rel="icon" href="{r('favicon.svg')}" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&amp;family=Figtree:wght@400;500;600&amp;display=swap" rel="stylesheet">
<link rel="stylesheet" href="{r('site.css')}">
{ld}
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="{r('')}">{LOGO}<span>Bridal Seamstress</span></a>
<nav class="main" aria-label="Main">
<a href="{r('')}#cities"{'' if path.startswith(('for-seamstresses', 'blog', 'wedding-dress-care')) else ' aria-current="page"'}>Find a seamstress</a>
<a href="{r('blog/')}"{' aria-current="page"' if path.startswith('blog') else ''}>Guides</a>
<a class="btn btn-dark" href="{r('for-seamstresses/')}">For seamstresses</a>
</nav>
</div></header>
{body}
<footer class="bot"><div class="wrap">
<span>Bridal Seamstress lists bridal sewing specialists across Australia. <a href="{r('for-seamstresses/')}">Add or claim a listing</a></span>
<span><strong style="color:var(--ink)">For seamstresses:</strong> <a href="https://thebridalsewingroom.com/" style="font-weight:600">Tools from The Bridal Sewing Room</a></span>
<span><a href="{r('blog/')}">Guides for brides</a></span>
{f'<span><a href="{r(CARE_PATH)}">Dress care essentials</a></span>' if CARE else ''}
<span>Run by <a href="https://customsewing.au">Rachel's Custom Sewing</a>, Toowoomba</span>
</div></footer>
</body>
</html>
"""


def write(path, content):
    fp = os.path.join(OUT, path, 'index.html') if (path == '' or path.endswith('/')) else os.path.join(OUT, path)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    open(fp, 'w').write(content)


def stars(L):
    if not L['rating']:
        return ''
    return f' · <span class="num">★ {e(L["rating"])}</span> ({e(f"{int(float(L["reviews"] or 0)):,}")} Google reviews)'


def claim_form(prefill_name='', prefill_city='', listing_url='', kind='claim'):
    opts = [('claim', 'Claim my free listing'), ('add', 'Add my business'), ('featured', 'Ask for a featured spot'),
            ('fix', 'Fix or remove a listing')]
    o = ''.join(f'<option value="{v}"{" selected" if v == kind else ""}>{t}</option>' for v, t in opts)
    return f"""<form class="claim" method="post" action="/api/claim" onsubmit="var b=this.querySelector('button[type=submit]');if(b.disabled)return false;b.disabled=true;b.textContent='Sending...'">
<label>I'd like to<select name="request">{o}</select></label>
<label>Business name<input name="business" type="text" required value="{e(prefill_name)}"></label>
<label>Your name<input name="name" type="text" required autocomplete="name"></label>
<label>Business email<input name="email" type="email" required autocomplete="email"></label>
<label>Town or suburb<input name="town" type="text" value="{e(prefill_city)}"></label>
<label>Bridal work you do<textarea name="services" rows="3"></textarea></label>
<label>How far ahead brides should book<input name="lead_time" type="text" placeholder="For example, 3 to 4 months before the wedding"></label>
<label>Photos of your bridal work (optional)<input name="photos" type="url" placeholder="Paste a Google Drive, Dropbox or Instagram link"><span style="font-size:13px;color:var(--mute);font-weight:400">Or email up to 3 photos to hello@bridalseamstress.com.au</span></label>
<label style="flex-direction:row;align-items:flex-start;gap:8px;font-weight:400"><input name="updates" type="checkbox" value="yes" style="margin-top:3px">Email me new tools for bridal seamstresses from The Bridal Sewing Room (optional, unsubscribe any time)</label>
<input type="hidden" name="listing" value="{e(listing_url)}">
<label class="hp" aria-hidden="true">Leave this empty<input name="website_url" type="text" tabindex="-1" autocomplete="off"></label>
<button class="btn btn-rose" type="submit">Send</button>
</form>"""


INTROS = {}
_ip = os.path.join(os.path.dirname(os.path.abspath(SRC)), 'city_intros.json')
if os.path.exists(_ip):
    INTROS = {k: v for k, v in json.load(open(_ip, encoding='utf-8')).items() if not k.startswith('_')}
COST_URL, TIME_URL = '/blog/how-much-do-wedding-dress-alterations-cost/', '/blog/how-long-do-wedding-dress-alterations-take/'


def faq_html(qas):
    return '<section class="faq"><h2 class="serif">Common questions</h2>' + ''.join(
        f'<details><summary>{e(q)}</summary><p>{a}</p></details>' for q, a in qas) + '</section>'


def faq_ld(qas):
    return {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': html.unescape(re.sub(r'<[^>]+>', '', a))}} for q, a in qas]}


def crumbs_ld(items):
    return {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': SITE + '/' + u} for i, (n, u) in enumerate(items)]}


FEATURED_COPY = 'A featured spot puts you at the top of your city page and shows up to 6 photos. It is free while our badge is on your website, linking to your listing.'

# ---------- city pages ----------
by_state = collections.defaultdict(list)
for c in cities.values():
    by_state[c['state']].append(c)

for c in cities.values():
    path = c['slug'] + '/'
    n = len(c['items'])
    present = [t for t in TAGS if any(t in L['tags'] for L in c['items'])]
    chips = '<button class="chip" type="button" aria-pressed="true" data-tag="">All bridal work</button>' + (
        '<button class="chip" type="button" aria-pressed="false" data-tag="Verified">Verified by owner</button>' if any(L['verified'] for L in c['items']) else '') + ''.join(
        f'<button class="chip" type="button" aria-pressed="false" data-tag="{e(t)}">{e(t)}</button>' for t in present)
    cards = []
    for L in c['items']:
        lp = f"{c['slug']}/{L['slug']}/"
        tg = ''.join(f'<span class="tag">{e(t)}</span>' for t in L['tags'][:4]) + (f'<span class="tag">+{len(L["tags"]) - 4} more</span>' if len(L['tags']) > 4 else '')
        cards.append(f"""<article class="card" data-tags="{e('|'.join(L['tags'] + (['Verified'] if L['verified'] else [])))}">
<div class="info">
{'<span class="feat">Featured</span>' if L['featured'] else ''}
<h2><a href="{rel(1, lp)}">{e(L['name'])}</a></h2>
<p class="meta">{e(L['suburb'])}{(' · also serves ' + e(L['serves'])) if L['serves'] else ''}{stars(L)}</p>
<p class="meta" style="color:var(--ink2)">{e(L['blurb'])}</p>
<div class="tags">{tg}</div>
</div>
<div class="act">
{f'<span class="ver">{VTICK}Verified by owner</span>' if L['verified'] else ''}
<span class="check">{TICK}Bridal work checked {CHECKED}</span>
<a class="btn btn-line" href="{rel(1, lp)}">View profile</a>
</div>
</article>""")
    nearby = [o for o in by_state[c['state']] if o is not c]
    near = ' · '.join(f'<a href="{rel(1, o["slug"] + "/")}">{e(o["name"])}</a>' for o in nearby) or f'<a href="{rel(1, "")}#cities">All cities</a>'
    word = 'business' if n == 1 else 'businesses'
    cn = c['name']
    intro = ''.join(f'<p>{e(x)}</p>' for x in INTROS.get(c['slug'], []))
    nver = sum(1 for L in c['items'] if L['verified'])
    ngown = sum(1 for L in c['items'] if 'Custom gowns' in L['tags'])
    nbus = [L for L in c['items'] if 'Bustles' in L['tags']]
    subs = [s for s, _ in collections.Counter(L['suburb'] for L in c['items'] if L['suburb'] != cn).most_common(4)]
    leads = [L for L in c['items'] if L['lead']][:2]
    qas = [(f'How many bridal seamstresses are there in {cn}?',
            f'We list {n} {cn} {word} that do wedding dress work, each checked by hand in {CHECKED}.'
            + (f' {nver} of them have been verified by the owner.' if nver > 1 else ' One of them has been verified by the owner.' if nver == 1 else '')
            + (f' You will find them in {", ".join(subs[:-1])} and {subs[-1]} as well as other suburbs.' if len(subs) > 1 else ''))]
    if ngown:
        qas.append((f'Can I find someone in {cn} who makes wedding dresses?',
                    f'Yes. {ngown} of the {cn} listings make gowns to order as well as, or instead of, altering them. Use the Custom gowns filter above to see them.'))
    if nbus:
        qas.append((f'Who adds bustles to wedding dresses in {cn}?',
                    ('These ' + str(len(nbus)) + ' listings mention bustles: ' if len(nbus) > 1 else 'This listing mentions bustles: ') +
                    ', '.join(f'<a href="{rel(1, c["slug"] + "/" + L["slug"] + "/")}">{e(L["name"])}</a>' for L in nbus[:6]) +
                    ('. Most other bridal seamstresses can add one too, so it is worth asking.' if len(nbus) <= 6 else ', with more on the list above.')))
    qas.append((f'How far ahead should I book wedding dress alterations in {cn}?',
                'Most bridal seamstresses say your first fitting should be six to eight weeks before the wedding, and many suggest booking that appointment as soon as you have your dress.'
                + ''.join(f' {e(L["name"])} says: {e(L["lead"].rstrip("."))}.' for L in leads)
                + f' Our <a href="{TIME_URL}">wedding dress alterations timeline</a> has the details.'))
    qas.append((f'How much do wedding dress alterations cost in {cn}?',
                'It depends on the dress and how much needs to change. As a guide, a simple hem on a one layer dress is usually $60 to $150, and taking in the side seams is usually $120 to $400. '
                f'Your seamstress will quote properly at the first fitting. See <a href="{COST_URL}">what wedding dress alterations cost</a> for a job by job list.'))
    body = f"""<section class="hero"><div class="wrap">
<p class="crumbs"><a href="{rel(1, '')}">Australia</a> › {e(STATE_NAMES[c['state']])} › {e(c['name'])}</p>
<h1 class="big">Bridal seamstresses in {e(c['name'])}</h1>
<p class="lede">{n} {e(c['name'])} {word} that do wedding dress alterations or make bridal gowns. We check every listing by hand, so you only see people who actually do bridal sewing.</p>
{f'<div class="intro">{intro}</div>' if intro else ''}
<div class="chips" role="group" aria-label="Filter by type of work">{chips}</div>
</div></section>
<main class="wrap cols">
<div class="colmain" id="results">
{''.join(cards)}
<p class="meta" id="count" aria-live="polite">Showing {n} of {n}</p>
{faq_html(qas)}
</div>
<aside class="colside">
<div class="panel dark">
<h3>Are you a {e(c['name'])} bridal seamstress?</h3>
<p>Your listing is free. Claim it to get a Verified by owner tick, add photos and tell brides how far ahead to book.</p>
<a class="btn btn-blush" style="align-self:flex-start" href="{rel(1, 'for-seamstresses/')}">Claim or add your listing</a>
</div>
<div class="panel">
<h3>Questions to ask before you book</h3>
<ul>
<li>How many fittings will my dress need?</li>
<li>Do you quote before you start, or after the first fitting?</li>
<li>Can you add a bustle, and which style suits my train?</li>
<li>How close to my date is too late to start?</li>
</ul>
</div>
<div class="panel">
<h3>Guides for brides</h3>
<p style="line-height:1.7"><a href="{COST_URL}">What alterations cost</a><br><a href="{TIME_URL}">When to start your fittings</a></p>
</div>
<div class="panel">
<h3>Nearby</h3>
<p style="line-height:1.7">{near}</p>
</div>
</aside>
</main>
<script>
(function(){{var chips=document.querySelectorAll('.chip'),cards=document.querySelectorAll('#results .card'),count=document.getElementById('count');
chips.forEach(function(b){{b.addEventListener('click',function(){{var t=b.getAttribute('data-tag'),shown=0;
chips.forEach(function(x){{x.setAttribute('aria-pressed',x===b?'true':'false')}});
cards.forEach(function(c){{var ok=!t||c.getAttribute('data-tags').split('|').indexOf(t)>-1;c.hidden=!ok;if(ok)shown++}});
count.textContent='Showing '+shown+' of '+cards.length;}})}});}})();
</script>"""
    ld = [{'@type': 'ItemList', 'name': f'Bridal seamstresses in {c["name"]}',
           'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'url': f"{SITE}/{c['slug']}/{L['slug']}/", 'name': L['name']}
                               for i, L in enumerate(c['items'])]},
          faq_ld(qas), crumbs_ld([('Australia', ''), (c['name'], path)])]
    write(path, page(1, path, f'Wedding dress alterations {c["name"]} | {n} bridal seamstress{"" if n == 1 else "es"}',
                     f'{n} hand-checked bridal seamstresses in {c["name"]}, {c["state"]} for wedding dress alterations and custom gowns. See suburbs, services and booking lead times.', body, ld))

# ---------- listing pages ----------
for L in listings:
    c = L['city']
    path = f"{c['slug']}/{L['slug']}/"
    tg = ''.join(f'<span class="tag">{e(t)}</span>' for t in L['tags'])
    acts = []
    if L['website']:
        acts.append(f'<a class="btn btn-dark" href="{e(L["website"])}" rel="nofollow noopener" target="_blank">Visit website</a>')
    if L['tel']:
        acts.append(f'<a class="btn btn-line" href="tel:{e(L["tel"])}">Call {e(L["phone"])}</a>')
    if L['maps']:
        acts.append(f'<a class="btn btn-line" href="{e(L["maps"])}" rel="nofollow noopener" target="_blank">Get directions</a>')
    body = f"""<main class="wrap cols" style="padding-top:36px">
<div class="colmain" style="gap:22px">
<p class="crumbs"><a href="{rel(2, c['slug'] + '/')}">{e(c['name'])}</a> › {e(L['suburb'])}</p>
<div style="display:flex;flex-direction:column;gap:8px">
<h1 class="big" style="font-size:46px">{e(L['name'])}</h1>
<p class="meta" style="font-size:16px">{e(L['suburb'])}, {e(L['state'])}{stars(L)}</p>
{f'<p class="meta" style="font-size:15px;color:var(--ink2)">Also serves {e(L["serves"])}</p>' if L['serves'] else ''}
<div style="display:flex;flex-wrap:wrap;gap:8px">{f'<span class="ver" title="The owner has confirmed these details">{VTICK}Verified by owner</span>' if L['verified'] else ''}<span class="check tag" style="padding:6px 10px">{TICK}Bridal work checked, {CHECKED}</span></div>
</div>
{('<div class="photos">' + ''.join(f'<img src="{rel(2, "photos/" + p)}" alt="Bridal work by {e(L["name"])}" loading="lazy" style="width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:12px">' for p in L['photos']) + '</div>' + ('<p class="meta" style="font-size:13px;margin-top:8px">Photos from their own website. Owner? Email hello@bridalseamstress.com.au to change or remove them.</p>' if any(p.startswith('web-') for p in L['photos']) else '')) if L['photos'] else ''}
<section class="blk">
<h2>Bridal services</h2>
<p class="meta" style="color:var(--ink2)">{e(L['blurb'])}</p>
{('<ul class="meta" style="color:var(--ink2);margin:0;padding-left:20px">' + ''.join(f'<li>{e(x)}</li>' for x in L['services']) + '</ul>') if L['services'] else ''}
<div class="tags">{tg}</div>
</section>
<section class="blk">
<h2>How far ahead to book</h2>
<p class="meta" style="color:var(--ink2)">{e(L['lead']) if L['lead'] else 'Ask when you get in touch. Busy bridal seamstresses often book out months ahead of wedding season.'}</p>
</section>
<section style="display:flex;flex-wrap:wrap;gap:12px">{''.join(acts)}</section>
<section class="blk" style="border-top:1px solid var(--line);padding-top:18px">
<h2>More bridal seamstresses in {e(c['name'])}</h2>
<p class="meta" style="line-height:1.8">{' · '.join(f'<a href="{rel(2, c["slug"] + "/" + o["slug"] + "/")}">{e(o["name"])}</a>' for o in [o for o in c['items'] if o is not L][:8])}{' · ' if len(c['items']) > 1 else ''}<a href="{rel(2, c['slug'] + '/')}">See all {len(c['items'])} in {e(c['name'])}</a></p>
</section>
</div>
<aside class="colside" style="gap:16px">
<div class="panel">
<h3>Questions to ask before you book</h3>
<ul>
<li>How many fittings will my dress need?</li>
<li>Do you quote before you start, or after the first fitting?</li>
<li>How close to my date is too late to start?</li>
</ul>
</div>
<div class="panel">
<h3>Guides for brides</h3>
<p style="line-height:1.7"><a href="{COST_URL}">What alterations cost</a><br><a href="{TIME_URL}">When to start your fittings</a></p>
</div>
<div class="owner">
{(f'''<p><strong>Verified by owner.</strong> The owner of {e(L['name'])} has confirmed these details. Need a change? Email <a href="mailto:hello@bridalseamstress.com.au">hello@bridalseamstress.com.au</a></p>''') if L['verified'] else (f'''<p>Own this business?</p>
<a class="btn btn-line btn-sm" href="{rel(2, 'claim/')}?{e(urlencode({'n': L['name'], 't': L['suburb'], 'l': path}))}" rel="nofollow">Claim this business</a>''')}
</div>
</aside>
</main>"""
    ld = {'@type': 'LocalBusiness', 'name': L['name'], 'url': L['website'] or None, '@id': SITE + '/' + path,
          'description': L['blurb'] + ((' Services: ' + ', '.join(L['services']) + '.') if L['services'] else ''),
          'image': [SITE + '/photos/' + p for p in L['photos']] or None, 'hasMap': L['maps'] or None,
          'telephone': L['tel'] or None, 'address': {'@type': 'PostalAddress', 'addressLocality': L['suburb'], 'addressRegion': L['state'], 'addressCountry': 'AU'},
          'areaServed': [a.strip() for a in re.sub(r'[()]', ',', L['serves']).replace(' and ', ',').split(',') if a.strip()] or None}
    write(path, page(2, path, f'{L["name"]}, {L["suburb"]} | Bridal Seamstress',
                     f'{L["name"]} in {L["suburb"]}, {L["state"]}.{(" Also serves " + L["serves"] + ".") if L["serves"] else ""} {L["blurb"]} Hand-checked for bridal work {CHECKED}.', body,
                     [{k: v for k, v in ld.items() if v}, crumbs_ld([('Australia', ''), (c['name'], c['slug'] + '/'), (L['name'], path)])]))

# ---------- home ----------
state_panels = []
for st in STATE_ORDER:
    if st not in by_state:
        continue
    cs = sorted(by_state[st], key=lambda c: -len(c['items']))
    links = ''.join(f'<li><a href="{rel(0, c["slug"] + "/")}">{e(c["name"])}</a> <span class="num" style="color:var(--mute)">({len(c["items"])})</span></li>' for c in cs)
    state_panels.append(f'<div class="panel"><h3>{e(STATE_NAMES[st])}</h3><ul style="list-style:none;padding:0">{links}</ul></div>')
total = len(listings)
HOME_QAS = [
    ('What is a bridal seamstress?', 'A bridal seamstress specialises in wedding dresses. They alter gowns to fit the bride, and some also make gowns from scratch. Many general alteration shops will take on a wedding dress, but a bridal specialist works with lace, beading and layered skirts every week.'),
    ('How do you check the listings?', f'We look at each business by hand for real wedding dress work, using their own website and Google reviews. If there is no sign of bridal sewing, they are not listed. Owners can claim their listing to confirm the details, and those show a Verified by owner tick. Listings were last checked in {CHECKED}.'),
    ('How do I find wedding dress alterations near me?', 'Pick your city in the list above, then filter by the work you need, such as bustles or custom gowns. Each listing shows the suburb, so you can choose someone close enough for three or four fittings.'),
    ('How far ahead should I book wedding dress alterations?', f'Most bridal seamstresses want your first fitting six to eight weeks before the wedding, and suggest booking it as soon as you have your dress. Seamstresses are busiest from July to November. Read our <a href="{TIME_URL}">alterations timeline</a> for more.'),
    ('How much do wedding dress alterations cost in Australia?', f'Most brides spend a few hundred dollars, depending on the dress. A simple one layer hem is usually $60 to $150, while a layered hem with a lace edge can be $250 to $600 or more. See <a href="{COST_URL}">what wedding dress alterations cost</a> for a full list.'),
    ('Does it cost anything to be listed?', 'No. Listings are free for bridal seamstresses. Seamstresses who add our badge to their own website get a featured spot at the top of their city page.'),
]
body = f"""<section class="hero"><div class="wrap hhero" style="padding-top:56px;padding-bottom:56px">
<div class="htext">
<h1 class="big">Find a seamstress who really does bridal</h1>
<p class="lede">On Google it is hard to tell a bridal specialist from a shop that mostly does hems and zips. Every business here has been checked by hand for wedding dress work. {total} listings across Australia so far.</p>
<p><a class="btn btn-dark" href="#cities">Choose your city</a></p>
</div>
<figure class="himg"><img src="{rel(0, 'photos/hero-october-falls.jpg')}" alt="A bride in a lace gown with sheer sleeves on her wedding morning" width="1000" height="1500" fetchpriority="high">
<figcaption>Photo: <a href="https://www.instagram.com/october_falls_photography/" target="_blank" rel="noopener">October Falls Photography</a></figcaption></figure>
</div></section>
<main class="wrap" style="padding-top:40px;padding-bottom:56px;display:flex;flex-direction:column;gap:24px" id="cities">
<h2 class="serif" style="margin:0;font-size:34px">Browse by city</h2>
<div class="statelist">{''.join(state_panels)}</div>
<div class="panel dark" style="margin-top:16px">
<h3>Are you a bridal seamstress?</h3>
<p>Listings are free. If you do wedding dress work and you are not here yet, tell us and we will check and add you.</p>
<a class="btn btn-blush" style="align-self:flex-start" href="{rel(0, 'for-seamstresses/')}">Add or claim your listing</a>
</div>
{faq_html(HOME_QAS)}
</main>"""
write('', page(0, '', 'Bridal Seamstress | Wedding dress alterations near you, hand-checked',
               f'Find a bridal seamstress near you for wedding dress alterations. {total} listings across Australia, each checked by hand for bridal work.', body,
               [{'@type': 'WebSite', 'name': 'Bridal Seamstress', 'url': SITE + '/', 'inLanguage': 'en-AU'},
                {'@type': 'Organization', 'name': 'Bridal Seamstress', 'url': SITE + '/', 'logo': SITE + '/favicon.svg', 'email': 'hello@bridalseamstress.com.au',
                 'description': 'A national directory of bridal seamstresses in Australia. Every listing is checked by hand for wedding dress work.',
                 'parentOrganization': {'@type': 'Organization', 'name': "Rachel's Custom Sewing", 'url': 'https://customsewing.au'}},
                faq_ld(HOME_QAS)]))

# ---------- for seamstresses ----------
body = f"""<section class="hero"><div class="wrap">
<h1 class="big">For bridal seamstresses</h1>
<p class="lede">Bridal Seamstress only lists people who do wedding dress work, so brides can find you without wading through general alteration shops.</p>
</div></section>
<main class="wrap cols">
<div class="colmain prose">
<h2>Your listing is free</h2>
<p>If you came up in our search we have probably already listed you. Claim your listing to get a Verified by owner tick, add photos and tell brides how far ahead to book. Verified listings show above unverified ones, and brides can filter for them. If you are not listed yet, use the form to ask, and we will check your bridal work before adding you.</p>
<h2>Featured spot</h2>
<p>{FEATURED_COPY} Featured listings show first on the city page with a small Featured label.</p>
<h2>Badge for your website</h2>
<p>Once your listing is live, add our badge to your own site with a link to your page. Tell us when it is up and we will make your listing featured.</p>
<p><img src="{rel(1, 'badge.svg')}" alt="Listed on Bridal Seamstress" width="220" height="64"></p>
<h2>Tools for your business</h2>
<p>The Bridal Sewing Room makes tools for bridal seamstresses, like price sheets, booking guides and a free pricing calculator. They come from a working bridal seamstress, so the times and methods are real.</p>
<p><a class="btn btn-dark" href="https://thebridalsewingroom.com/">See the tools</a> <a href="https://rachelscustomsewing.gumroad.com/subscribe" style="margin-left:12px">Hear when new ones come out</a></p>
<h2>Changes or removal</h2>
<p>If something on your listing is wrong, or you would rather not be listed, choose that option in the form and we will sort it out.</p>
</div>
<aside class="colside panel soft" style="padding:26px;gap:14px">
<h2 class="serif" style="margin:0;font-size:28px">Get in touch</h2>
{claim_form()}
</aside>
</main>"""
write('for-seamstresses/', page(1, 'for-seamstresses/', 'For bridal seamstresses | Bridal Seamstress',
                                'Claim or add your free listing on Bridal Seamstress, the hand-checked directory of bridal seamstresses in Australia.', body))

# ---------- claim page (linked from each unverified listing) ----------
body = f"""<main class="wrap cols" style="padding-top:36px;padding-bottom:56px">
<div class="colmain prose">
<p class="crumbs"><a id="back" href="{rel(1, '')}">Back to the directory</a></p>
<h1 class="big" style="font-size:44px">Claim <span id="biz">your listing</span></h1>
<p>Your listing is free. Claim it to get a Verified by owner tick, add photos and tell brides how far ahead to book. Verified listings show above unverified ones, and brides can filter for them.</p>
<h2>Want to be seen first?</h2>
<p>{FEATURED_COPY}</p>
<h2>Tools for bridal seamstresses</h2>
<p>Price sheets, booking guides and a free pricing calculator from <a href="https://thebridalsewingroom.com/">The Bridal Sewing Room</a>, made by a working bridal seamstress.</p>
</div>
<aside class="colside panel soft" style="padding:26px;gap:14px">
<h2 class="serif" style="margin:0;font-size:28px">Claim your free listing</h2>
{claim_form()}
</aside>
</main>
<script>
(function(){{var q=new URLSearchParams(location.search),n=q.get('n'),t=q.get('t'),l=q.get('l');
if(!l||!/^[a-z0-9-]+\\/[a-z0-9-]+\\/$/.test(l))return;
var f=document.querySelector('form.claim');
if(n){{f.business.value=n;document.getElementById('biz').textContent=n;}}
if(t)f.town.value=t;
f.listing.value='{SITE}/'+l;document.getElementById('back').href='/'+l;document.getElementById('back').textContent='Back to the listing';}})();
</script>"""
write('claim/', page(1, 'claim/', 'Claim your listing | Bridal Seamstress', 'Claim your free listing on Bridal Seamstress.', body).replace('<meta name="viewport"', '<meta name="robots" content="noindex">\n<meta name="viewport"', 1))

# ---------- thanks + 404 ----------
body = f"""<section class="hero"><div class="wrap" style="padding-top:64px;padding-bottom:64px">
<h1 class="big">Thanks, that's come through</h1>
<p class="lede">Rachel reads every request herself and will reply by email, usually within a couple of days.</p>
<p>Running a bridal sewing business? <a href="https://rachelscustomsewing.gumroad.com/subscribe">Get new tools for seamstresses</a> from The Bridal Sewing Room.</p>
<p><a href="{rel(1, '')}">Back to the directory</a></p>
</div></section>"""
write('thanks/', page(1, 'thanks/', 'Thanks | Bridal Seamstress', 'Your request has been sent.', body))
body = f"""<section class="hero"><div class="wrap" style="padding-top:64px;padding-bottom:64px">
<h1 class="big">That page isn't here</h1>
<p class="lede">The listing may have moved. <a href="/">Browse by city</a> to find it.</p>
</div></section>"""
open(os.path.join(OUT, '404.html'), 'w').write(page(0, '404', 'Page not found | Bridal Seamstress', 'Page not found.', body))


# ---------- blog ----------
BLOG_DIR = os.path.join(os.path.dirname(os.path.abspath(SRC)), 'blog')
BLOG_PHOTOS = {  # marker file name in the draft -> (photo in data/photos, alt override or None)
    'Paige Lamb - after hero.png': ('blog-paige-lamb-after.jpg', None),
    'Karyn-2PointBustle.png': ('blog-karyn-2-point-bustle.jpg', None),
    '1. Richelle Joliffe - hem close up.png': ('blog-richelle-hem-restoration.jpg', 'Wedding dress hem before and after a tulle repair and restoration clean'),
    'Emmalee English - black gown tulle split b-a.png': ('blog-emmalee-black-gown.jpg', None),
    '3. Grace Halligan - bustle down up.png': ('blog-grace-bustle-down-up.jpg', None),
}


def md_inline(t):
    t = e(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    def lk(m):
        url = m.group(2)
        ext = url.startswith('http') and 'bridalseamstress.com.au' not in url
        return f'<a href="{url}"' + (' target="_blank" rel="noopener"' if ext else '') + f'>{m.group(1)}</a>'
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lk, t)


def md_to_html(md):
    out, para, lines = [], [], md.split('\n')
    i = 0
    def flush():
        if para:
            out.append('<p>' + md_inline(' '.join(para)) + '</p>'); para.clear()
    while i < len(lines):
        ln = lines[i].rstrip()
        m = re.match(r'\[Photo:\s*(.+?)\s*\|\s*alt:\s*(.+?)\s*\|\s*caption:.*\]$', ln)
        if m:
            flush()
            fn, alt = BLOG_PHOTOS.get(m.group(1), (None, None))
            if fn:
                out.append(f'<figure class="bimg"><img src="/photos/{fn}" alt="{e(alt or m.group(2))}" loading="lazy">'
                           '<figcaption>Photo: <a href="https://www.rachelscustomsewing.com.au/" target="_blank" rel="noopener">Rachel\'s Custom Sewing, Toowoomba</a></figcaption></figure>')
        elif ln.startswith('### '):
            flush(); out.append('<h3>' + md_inline(ln[4:]) + '</h3>')
        elif ln.startswith('## '):
            flush(); out.append('<h2>' + md_inline(ln[3:]) + '</h2>')
        elif ln.startswith('# '):
            flush()
        elif ln.startswith('|'):
            flush(); rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'-+', c) for c in cells):
                    rows.append(cells)
                i += 1
            i -= 1
            out.append('<div class="tblwrap"><table><thead><tr>' + ''.join(f'<th>{md_inline(c)}</th>' for c in rows[0]) + '</tr></thead><tbody>' +
                       ''.join('<tr>' + ''.join(f'<td>{md_inline(c)}</td>' for c in r) + '</tr>' for r in rows[1:]) + '</tbody></table></div>')
        elif ln.startswith('- '):
            flush(); items = []
            while i < len(lines) and lines[i].startswith('- '):
                items.append('<li>' + md_inline(lines[i][2:]) + '</li>'); i += 1
            i -= 1
            out.append('<ul>' + ''.join(items) + '</ul>')
        elif ln.strip() == '---':
            flush(); out.append('<hr>')
        elif not ln.strip():
            flush()
        else:
            para.append(ln.strip())
        i += 1
    flush()
    return '\n'.join(out)


posts = []
if os.path.isdir(BLOG_DIR):
    for fn in sorted(os.listdir(BLOG_DIR)):
        if not fn.endswith('.md'):
            continue
        raw = open(os.path.join(BLOG_DIR, fn), encoding='utf-8').read()
        notes, content = raw.split('\n---\n', 1) if raw.startswith('---') else ('', raw)
        content = content.lstrip('-\n')
        title = re.search(r'^# (.+)$', content, re.M).group(1).strip()
        seo_title = re.search(r'\*\*SEO Title\*\*[^:]*:\s*(.+)', notes).group(1).strip()
        meta = re.search(r'\*\*Meta Description\*\*[^:]*:\s*(.+)', notes).group(1).strip()
        slug = re.search(r'\*\*URL Slug:\*\*\s*`/?(.+?)/?`', notes).group(1).strip('/') + '/'
        mins = (re.search(r'\*\*Reading time:\*\*\s*(.+)', notes) or [None, ''])[1].strip()
        first_img = next((v[0] for k, v in BLOG_PHOTOS.items() if k in content), None)
        posts.append({'title': title, 'seo': seo_title, 'meta': meta, 'path': slug, 'mins': mins, 'html': md_to_html(content), 'img': first_img})

for P in posts:
    body = f"""<main class="wrap" style="padding-top:40px;padding-bottom:64px">
<article class="prose blog">
<p class="crumbs"><a href="/blog/">Guides for brides</a></p>
<h1 class="big" style="font-size:44px">{e(P['title'])}</h1>
<p class="meta">{e(P['mins'])} read · Bridal Seamstress</p>
{P['html']}
</article>
</main>"""
    ld = {'@context': 'https://schema.org', '@type': 'Article', 'headline': P['title'], 'description': P['meta'],
          'publisher': {'@type': 'Organization', 'name': 'Bridal Seamstress', 'url': SITE},
          'image': SITE + '/photos/' + P['img'] if P['img'] else None, 'mainEntityOfPage': SITE + '/' + P['path']}
    write(P['path'], page(2, P['path'], P['seo'] + ' | Bridal Seamstress', P['meta'], body, ld))

if posts:
    cards = ''.join(f"""<a class="panel bcard" href="/{P['path']}">{f'<img src="/photos/{P["img"]}" alt="" loading="lazy">' if P['img'] else ''}<h2 style="margin:0;font-size:22px">{e(P['title'])}</h2><p class="meta">{e(P['meta'])}</p></a>""" for P in posts)
    body = f"""<section class="hero"><div class="wrap">
<h1 class="big">Guides for brides</h1>
<p class="lede">Straight answers about wedding dress alterations, from what they cost to when to book your first fitting.</p>
</div></section>
<main class="wrap" style="padding-top:40px;padding-bottom:64px"><div class="bgrid">{cards}</div>
{f'<a class="panel" href="/{CARE_PATH}" style="margin-top:24px;text-decoration:none;color:var(--ink);background:var(--blush);border:0"><h3>Wedding dress care essentials</h3><p class="meta">What to buy for your dress, from the right bra for fittings to a box for storing it afterwards.</p></a>' if CARE else ''}</main>"""
    write('blog/', page(1, 'blog/', 'Guides for brides | Bridal Seamstress', 'Guides for brides on wedding dress alterations in Australia: costs, timing and how to choose a bridal seamstress.', body))

# ---------- dress care essentials (affiliate picks) ----------
if CARE:
    def care_item(it):
        btn = ''
        if it.get('link'):
            btn = f'<a class="btn btn-rose btn-sm" href="{e(it["link"])}" target="_blank" rel="sponsored nofollow noopener">See it on {e(it.get("retailer") or "the shop")}</a>'
        img = f'<img src="{e(it["img"])}" alt="" loading="lazy" style="width:100%;max-width:220px;border-radius:10px">' if it.get('img') else ''
        look = f'<p class="meta"><strong>Look for:</strong> {e(it["look_for"])}</p>' if it.get('look_for') else ''
        return f'<div class="panel">{img}<h3>{e(it["name"])}</h3><p>{e(it["why"])}</p>{look}{btn}</div>'
    live = [it for sec in CARE['sections'] for it in sec['items'] if it.get('link')]
    amazon = any('amazon' in (it.get('retailer') or '').lower() for it in live)
    secs = ''.join(f"""<section class="blk" style="margin-top:28px"><h2 class="serif" style="font-size:30px">{e(sec['title'])}</h2>
<p style="margin:0;color:var(--ink2);max-width:720px">{e(sec['intro'])}</p>
<div class="statelist" style="margin-top:6px">{''.join(care_item(it) for it in sec['items'])}</div></section>""" for sec in CARE['sections'])
    disclose = ('Some links on this page are affiliate links. If you buy through one, Bridal Seamstress may earn a small commission. '
                'It costs you nothing extra, and no brand pays to be on this list.' + (' As an Amazon Associate we earn from qualifying purchases.' if amazon else ''))
    body = f"""<section class="hero"><div class="wrap">
<p class="crumbs"><a href="{rel(1, 'blog/')}">Guides for brides</a></p>
<h1 class="big">Wedding dress care essentials</h1>
<p class="lede">The handful of things worth buying for your dress, from the first fitting until you pack it away. Picked by a bridal seamstress who sees what goes wrong.</p>
<p class="meta" style="max-width:720px">{e(disclose)}</p>
</div></section>
<main class="wrap" style="padding-top:12px;padding-bottom:64px">
{secs}
<section class="panel dark" style="margin-top:40px">
<h3>Still need alterations?</h3>
<p>Every seamstress in our directory has been checked to make sure they do bridal work. Read <a href="{rel(1, COST_URL.strip('/') + '/')}" style="color:#fff">what alterations cost</a> or <a href="{rel(1, TIME_URL.strip('/') + '/')}" style="color:#fff">how long they take</a>, then find someone near you.</p>
<a class="btn btn-blush" style="align-self:flex-start" href="{rel(1, '')}#cities">Find a bridal seamstress</a>
</section>
</main>"""
    write(CARE_PATH, page(1, CARE_PATH, 'Wedding dress care essentials: what to buy for your dress | Bridal Seamstress',
                          'What to buy for your wedding dress, from the right bra for fittings to a garment bag, steamer and preservation box. Chosen by a bridal seamstress.', body,
                          crumbs_ld([('Guides for brides', 'blog/'), ('Wedding dress care essentials', CARE_PATH)])))

# ---------- assets ----------
open(os.path.join(OUT, 'site.css'), 'w').write(CSS.strip() + '\n')
PHOTO_SRC = os.path.join(os.path.dirname(os.path.abspath(SRC)), 'photos')
if os.path.isdir(PHOTO_SRC):
    shutil.copytree(PHOTO_SRC, os.path.join(OUT, 'photos'), dirs_exist_ok=True)
open(os.path.join(OUT, 'favicon.svg'), 'w').write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" fill="none" stroke="#9C3F55" stroke-width="1.8"><circle cx="14" cy="14" r="12" fill="#fff"/><path d="M8 20 L20 8"/><circle cx="19" cy="9" r="1.6"/></svg>\n')
open(os.path.join(OUT, 'badge.svg'), 'w').write('''<svg xmlns="http://www.w3.org/2000/svg" width="220" height="64" viewBox="0 0 220 64" role="img" aria-label="Listed on Bridal Seamstress">
<rect x="1" y="1" width="218" height="62" rx="12" fill="#F7EEF0" stroke="#9C3F55"/>
<g fill="none" stroke="#9C3F55" stroke-width="1.6" transform="translate(14 18)"><circle cx="14" cy="14" r="12"/><path d="M8 20 L20 8"/><circle cx="19" cy="9" r="1.6"/></g>
<text x="52" y="27" font-family="Figtree,Arial,sans-serif" font-size="11" fill="#5A5E70">Hand-checked listing on</text>
<text x="52" y="46" font-family="Cormorant Garamond,Georgia,serif" font-size="20" font-weight="600" fill="#1E2235" textLength="154" lengthAdjust="spacingAndGlyphs">Bridal Seamstress</text>
</svg>
''')
open(os.path.join(OUT, 'robots.txt'), 'w').write(f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')
urls = [''] + ['for-seamstresses/'] + (['blog/'] + [P['path'] for P in posts] if posts else []) + ([CARE_PATH] if CARE else []) + [c['slug'] + '/' for c in cities.values()] + [f"{L['city']['slug']}/{L['slug']}/" for L in listings]
open(os.path.join(OUT, 'sitemap.xml'), 'w').write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
                                                 ''.join(f'<url><loc>{SITE}/{u}</loc><lastmod>{TODAY}</lastmod></url>\n' for u in urls) + '</urlset>\n')
llms = ['# Bridal Seamstress', '',
        f'> A national directory of bridal seamstresses in Australia: {total} businesses that do wedding dress alterations or make bridal gowns, each checked by hand for bridal work (last checked {CHECKED}). Free to use, run by Rachel\'s Custom Sewing in Toowoomba, QLD.', '',
        'Each city page lists hand-checked bridal seamstresses with suburb, services such as bustles or custom gowns, owner-verified status and booking lead times where known. Each listing page has contact details and services.', '',
        '## Guides for brides', ''] + [f'- [{P["title"]}]({SITE}/{P["path"]}): {P["meta"]}' for P in posts] + ([f'- [Wedding dress care essentials]({SITE}/{CARE_PATH}): what to buy for your dress, from fittings to storage'] if CARE else []) + ['', '## Bridal seamstresses by city', ''] + [
        f'- [Bridal seamstresses in {c["name"]}, {STATE_NAMES[c["state"]]}]({SITE}/{c["slug"]}/): {len(c["items"])} listings' for st in STATE_ORDER for c in sorted(by_state.get(st, []), key=lambda c: -len(c['items']))] + [
        '', '## For seamstresses', '', f'- [Claim or add a free listing]({SITE}/for-seamstresses/)', '- [The Bridal Sewing Room](https://thebridalsewingroom.com/): pricing and business tools for bridal seamstresses', '']
open(os.path.join(OUT, 'llms.txt'), 'w').write('\n'.join(llms))

# outreach merge list (not published): one row per listing with an email
with open(os.path.join(os.path.dirname(OUT.rstrip('/')), 'outreach-list.csv'), 'w') as f:
    import csv
    w = csv.writer(f)
    w.writerow(['business', 'city', 'email', 'listing_url', 'place_id'])
    for L in listings:
        if L['email']:
            w.writerow([L['name'], L['city']['name'], L['email'], f"{SITE}/{L['city']['slug']}/{L['slug']}/", L['place_id']])

print(f'{len(cities)} cities, {total} listings, {sum(1 for L in listings if L["email"])} with email')
