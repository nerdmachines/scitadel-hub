"""S-015: measure what the corpus takes as tessera blocks. Re-fetches the scholarly-type works of the S-013 manifest, extracts the
document-model tables and the figures (CPU only), encodes them, lists the OpenAlex snapshot partitions, and writes `tsra.json`
(aggregates only; scratch is deleted by the caller). Network and process code; the arithmetic is in core.py, the encoders in tsra.py."""
import concurrent.futures as cf
import hashlib
import json
import re
import subprocess
import urllib.parse
from pathlib import Path

from . import core, tsra
from .run import EPMC, MAX_PDF, TOKENIZER, http, records_for, robots_ok

PMC = 'https://pmc-oa-opendata.s3.amazonaws.com/'
S3 = 'https://openalex.s3.amazonaws.com/'
NOT_GRAPHIC = ('.xml', '.json', '.txt', '.pdf')
EXTRACTOR = 'sizing-s015@0.1 (jats | pdftotext -bbox-layout)'


def num(url):
    m = re.search(r'(\d+)$', url or '')
    return int(m[1]) if m else 0


def jxl(path, tmp):
    """`(file, input bytes, how)`: the lossless JPEG XL file of an image, as the plan keeps figures: a JPEG is transcoded (reconstructable bit-exactly), a raster
    is encoded at distance 0; formats cjxl cannot read (JPEG 2000, JBIG2, CCITT, TIFF) stay as they are."""
    out, size = Path(tmp) / (path.name + '.jxl'), path.stat().st_size
    if path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif'):
        try:
            args = ['cjxl', str(path), str(out), '--quiet'] + (['-d', '0'] if path.suffix.lower() != '.jpg' else [])
            if subprocess.run(args, capture_output=True, timeout=180).returncode == 0:
                return out, size, 'jxl'
        except subprocess.TimeoutExpired:
            pass
    return path, size, 'native'


def pdf_figures(pdf, tmp, wid):
    """The figures of a PDF (`core.figure_images`: each object once, no mask or icon): native bytes and bytes after the plan's lossless
    encoding of each; and the counts of `pdfimages -list` rows and of objects, for the record."""
    lst = subprocess.run(['pdfimages', '-list', str(pdf)], capture_output=True, timeout=300).stdout.decode('utf-8', 'replace')
    imgs = core.parse_pdfimages_list(lst)
    for i, im in enumerate(imgs):
        im['idx'] = i
    figs = core.figure_images(imgs)
    d = Path(tmp) / 'img' / wid
    d.mkdir(parents=True, exist_ok=True)
    if figs:
        subprocess.run(['pdfimages', '-all', str(pdf), str(d / 'i')], capture_output=True, timeout=600)
    files = sorted(d.glob('i-*'))
    for im in figs:
        f = files[im['idx']] if im['idx'] < len(files) else None
        if f is None:
            im.update(native=im['bytes'], jxl=im['bytes'], how='missing')
            continue
        out, im['native'], im['how'] = jxl(f, d)
        im['jxl'] = out.stat().st_size
        (Path(tmp) / 'blobs').mkdir(exist_ok=True)
        out.replace(Path(tmp) / 'blobs' / f'{wid}-{f.name}')
    for f in d.glob('*'):
        f.unlink()
    d.rmdir()
    return figs, {'placements': len(imgs), 'objects': len({im['obj'] for im in imgs})}


def pmc_graphics(pmcid, units, tmp, wid):
    """The figure and table graphics of a PMC article (keyless listing of the open-data bucket; `core.pick_graphic_files` chooses one
    rendition per graphic of the article's own JATS), downloaded and encoded; and the bytes of everything else, the supplementary material."""
    xml = http(f'{PMC}?list-type=2&prefix={pmcid}.', 0.2, 2**24).decode()
    files = [(k.rsplit('/', 1)[-1], int(sz)) for k, sz in re.findall(r'<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>', xml) if '/' in k]
    chosen = core.pick_graphic_files(units, files)
    out = []
    for name, size in chosen:
        f = Path(tmp) / 'img' / f'{wid}-{name}'
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(http(PMC + urllib.parse.quote(f'{pmcid}.1/{name}'), 0.2, MAX_PDF))
        o, native, how = jxl(f, f.parent)
        out.append({'name': name, 'native': native, 'jxl': o.stat().st_size, 'how': how, 'bytes': size})
        for g in (f, o):
            g.unlink(missing_ok=True)
    rest = core.other_files(files, chosen)
    return out, {'files': len(rest), 'bytes': sum(b for _, b in rest), 'image_files': sum(n.rpartition('.')[2].lower() in core.IMAGE_EXT for n, _ in rest)}


def extract(rec, tok, tmp):
    """One work -> the rows of every table, the figure measurements and the route/status; saved as JSON in `tmp/rows`."""
    wid = rec['id'].rsplit('/', 1)[-1]
    f = Path(tmp) / 'rows' / f'{wid}.json'
    if f.exists():
        return json.loads(f.read_text())
    loc = rec.get('best_oa_location') or {}
    route = core.route_of(rec)
    row = {'id': wid, 'route': route, 'status': 'ok', 'elements': [], 'chunks': [], 'figs': [], 'images': [], 'cells': [], 'xrefs': [], 'bib': [],
           'input_hash': '', 'input_url': '', 'meta': {
               'doi': rec.get('doi') or '', 'licence': loc.get('license') or '', 'type': rec.get('type') or '', 'title': rec.get('title') or '',
               'year': rec.get('publication_year') or 0, 'language': rec.get('language') or '', 'cited_by': rec.get('cited_by_count') or 0,
               'venue': num((loc.get('source') or {}).get('id')),
               'authorships': [[num((a.get('author') or {}).get('id')), (a.get('author') or {}).get('display_name') or '',
                                num(((a.get('institutions') or [{}])[0] or {}).get('id'))] for a in rec.get('authorships') or []],
               'cites': [num(w) for w in rec.get('referenced_works') or []]}}
    try:
        if route == 'jats':
            try:  # as S-013: a JATS that cannot be fetched or parsed falls back to the PDF
                xml = http(EPMC.format(core.pmcid_of(rec)), 0.2, MAX_PDF)
                b = core.jats_blocks(xml)
                row.update(input_hash=hashlib.sha256(xml).hexdigest(), input_url=EPMC.format(core.pmcid_of(rec)),
                           elements=[[e['kind'], e['text'], e['parent'], 0, 0, 0, 0, 0] for e in b['elements']], xrefs=b['xrefs'], bib=b['bib'], cells=b['tables'])
                try:
                    imgs, row['supplementary'] = pmc_graphics(core.pmcid_of(rec), b['graphics'], tmp, wid)
                    by = {core._base(g['name']): g for g in imgs}
                except Exception:
                    imgs, by, row['graphics_miss'] = [], {}, True  # the text is good, the graphics listing is not: counted, and the figure bytes of this work are 0
                row['images'] = imgs
                row['figs'] = [{'id': g['id'], 'caption': g['caption'], 'page': 0, 'jxl': sum(by.get(core._base(h), {}).get('jxl', 0) for h in g['graphics'])} for g in b['figs']]
            except Exception:
                route = row['route'] = 'pdf' if loc.get('pdf_url') else 'unresolved'
                row.update(jats_miss=True, elements=[], xrefs=[], bib=[], cells=[], images=[], figs=[])
        if route == 'pdf':
            url = loc['pdf_url']
            if not robots_ok(url):
                row['status'] = 'robots'
            else:
                data = http(url, 1.0, MAX_PDF)
                if not data.startswith(b'%PDF'):
                    row['status'] = 'not_pdf'
                else:
                    p = Path(tmp) / 'pdf' / f'{wid}.pdf'
                    p.parent.mkdir(exist_ok=True)
                    p.write_bytes(data)
                    row.update(input_hash=hashlib.sha256(data).hexdigest(), input_url=url, pdf_bytes=len(data))
                    try:
                        lay = subprocess.run(['pdftotext', '-enc', 'UTF-8', '-bbox-layout', str(p), '-'], capture_output=True, timeout=300).stdout
                        row['elements'] = [['paragraph', t, -1, pg, *bb] for pg, bb, t in core.pdf_layout_blocks(lay)]
                        row['images'], row['image_stats'] = pdf_figures(p, tmp, wid)
                        row['figs'] = [{'id': f'img{i}', 'caption': -1, 'page': im['page'], 'jxl': im['jxl']} for i, im in enumerate(row['images'])]
                        row['status'] = 'ok' if row['elements'] else 'no_text'
                    finally:
                        p.unlink(missing_ok=True)
        if route == 'unresolved':
            row['status'] = 'unresolved'
    except Exception as e:
        row['status'] = 'fetch_' + type(e).__name__
    if row['elements'] and tok is not None:
        texts = [e[1] for e in row['elements']]
        counts = [len(e.ids) for e in tok.encode_batch(texts, add_special_tokens=False)]
        row['chunks'] = [list(c) for c in core.pack_chunks(counts, 350)]
        row['qc'] = [len(texts), sum(counts), sum(map(len, texts))]
        row['content_hash'] = hashlib.sha256('\n'.join(texts).encode()).hexdigest()
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(row))
    return row


def table_rows(rows):
    """Rows of every table of `tsra.TABLES` from the extracted works, sorted by (work_id, ord); returns them and the figure blob files."""
    t = {k: [] for k in tsra.TABLES}
    for r in sorted(rows, key=lambda r: num(r['id'])):
        w, m = num(r['id']), r['meta']
        els = r['elements']
        qc = r.get('qc', [0, 0, 0])
        t['works'].append((w, m['doi'], m['licence'], 'pdf' if r['route'] == 'pdf' else r['route'], EXTRACTOR if els else '', r.get('content_hash', ''),
                           r['input_hash'], r['input_url'], *qc, 1 if els else 0, m['type'], m['title'], m['year'], m['language'], m['cited_by'], m['venue']))
        t['authorships'] += [(w, i, *a) for i, a in enumerate(m['authorships'])]
        t['citations'] += [(w, c) for c in m['cites']]
        t['elements'] += [(w, i, e[2], e[0], e[1], e[3], *e[4:]) for i, e in enumerate(els)]
        t['chunks'] += [(w, i, *c) for i, c in enumerate(r['chunks'])]
        t['figures'] += [(w, g['id'], g['caption'], g['page'], 0, 0, 0, 0, len(t['figures']), g['jxl']) for g in r['figs']]
        t['table_cells'] += [(w, *c[:4], c[4], '') for c in r['cells']]
        t['inline_refs'] += [(w, *x) for x in r['xrefs']]
        t['bib'] += [(w, b['id'], b['title'], b['authors'], b['year'], b['doi'], 0) for b in r['bib']]
    return t


def figure_factors(rows):
    """Per covered work (a work with text): embedded or linked image bytes, bytes after the lossless encoding, images and figures."""
    cov = [r for r in rows if r['elements']]
    pdf = [r for r in cov if r['route'] == 'pdf']
    jats = [r for r in cov if r['route'] == 'jats']
    emb = lambda r: sum(i['bytes'] for i in r['images'])  # noqa: E731
    f = {'fig_blob_bytes': [sum(i['jxl'] for i in r['images']) for r in cov], 'fig_native_bytes': [sum(i['native'] for i in r['images']) for r in cov],
         'fig_embedded_bytes': [emb(r) for r in cov], 'images_per_paper': [len(r['images']) for r in cov], 'figs_per_paper': [len(r['figs']) for r in cov]}
    out = {k: core.summarize(v) for k, v in f.items()}
    out['by_route'] = {name: {k: core.summarize([fn(r) for r in rs]) for k, fn in (
        ('fig_blob_bytes', lambda r: sum(i['jxl'] for i in r['images'])), ('embedded_bytes', emb), ('native_bytes', lambda r: sum(i['native'] for i in r['images'])), ('images', lambda r: len(r['images'])), ('figs', lambda r: len(r['figs'])))}
        for name, rs in (('pdf', pdf), ('jats', jats))}
    out['pdf_image_share_of_pdf'] = sum(emb(r) for r in pdf) / max(1, sum(r.get('pdf_bytes', 0) for r in pdf))
    out['supplementary'] = {k: core.summarize([r.get('supplementary', {}).get(k, 0) for r in jats]) for k in ('bytes', 'files', 'image_files')}
    out['pdf_objects'] = {k: core.summarize([r.get('image_stats', {}).get(k, 0) for r in pdf]) for k in ('placements', 'objects')}
    out['graphics_miss'] = sum(bool(r.get('graphics_miss')) for r in cov)
    out['how'] = {h: sum(i.get('how') == h for r in cov for i in r['images']) for h in ('jxl', 'native', 'missing')}
    return out


def s3_list(prefix):
    """All `(key, size)` under a prefix of the keyless OpenAlex bucket."""
    out, token = [], None
    while True:
        q = {'list-type': 2, 'prefix': prefix, **({'continuation-token': token} if token else {})}
        xml = http(S3 + '?' + urllib.parse.urlencode(q), 0.2, 2**26).decode()
        out += [(k, int(s)) for k, s in re.findall(r'<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>', xml)]
        m = re.search(r'<NextContinuationToken>([^<]+)', xml)
        if not m:
            return out
        token = m[1]


def snapshot_deltas(release, previous):
    """OpenAlex snapshot generation and delta bytes, per format, for each previous release date. Only the current release is in the
    bucket (every object carries its date), so a generation's delta is the `updated_date` partitions on or after the previous release."""
    out = {'release': release, 'previous': previous, 'formats': {}}
    for fmt in ('jsonl', 'parquet'):
        objs = s3_list(f'data/{fmt}/')
        out['formats'][fmt] = {since: core.snapshot_generation(objs, since) for since in previous}
    return out


def encode(rows, tmp, rounds, seed):
    """Everything measured from the extracted works: tables, ranges, vectors, overhead, figure blobs."""
    t = table_rows(rows)
    n = len(rows)
    cov = [r for r in rows if r['elements']]
    n_text, n_jats = len(cov), sum(r['route'] == 'jats' for r in cov)
    tmp = Path(tmp)
    (tmp / 'enc').mkdir(exist_ok=True)
    tables = tsra.measure_tables(t, tmp / 'enc', n)
    grp = {g: sum(v['tsra'] for k, v in tables.items() if v['group'] == g and '.' not in k) for g in ('meta', 'doc', 'jats')}
    grp['text'] = tables['elements.text']['tsra']
    rngs = tsra.shard_range(t, tmp / 'enc', [num(r['id']) for r in rows], {num(r['id']): (bool(r['elements']), r['route'] == 'jats' and bool(r['elements'])) for r in rows}, rounds, seed)
    per = core.per_paper(grp, n, n_text, n_jats)
    factors = {k: {'n': n if k == 'meta' else n_text, 'mean': v, 'ci95': [min([v] + [x[k] for x in rngs]), max([v] + [x[k] for x in rngs])]} for k, v in per.items()}
    blobs = [p.read_bytes() for p in sorted((tmp / 'blobs').glob('*'))[:2000]] if (tmp / 'blobs').exists() else []
    return {'n_works': n, 'n_with_text': n_text, 'n_jats_with_text': n_jats, 'tables': tables, 'group_bytes': grp, 'bytes_per_paper': per,
            'factors': {f'tsra_{k}': v for k, v in factors.items()}, 'subset_range_rounds': rounds,
            'chunk_rows_per_paper': tables['chunks']['rows'] / max(1, n_text), 'element_rows_per_paper': tables['elements']['rows'] / max(1, n_text),
            'vectors': {str(d): tsra.vector_bytes(d, 50000, tmp / 'enc') for d in (512, 1024)}, 'overhead': tsra.overhead(tmp / 'enc'),
            'blob_vortex': {'blobs': len(blobs), 'payload_bytes': sum(map(len, blobs)), 'vortex_bytes': tsra.blob_file(blobs, tmp / 'enc') if blobs else 0},
            'figures': figure_factors(rows)}


def versions():
    from importlib.metadata import version
    cj = subprocess.run(['cjxl', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    return {'tessera_py': version('tessera'), 'vortex_data': version('vortex-data'), 'cjxl': cj,
            'pdfimages': subprocess.run(['pdfimages', '-v'], capture_output=True, text=True).stderr.splitlines()[0]}


def cmd_tsra(a, tool_versions):
    from tokenizers import Tokenizer
    out, tmp = Path(a.out), Path(a.scratch)
    tmp.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    man = json.loads(Path(a.manifest).read_text())
    ids = man['work_ids'][:a.limit] if a.limit else man['work_ids']
    recs = json.loads(next(q for q in (Path(a.records), Path(__file__).resolve().parents[1] / a.records) if q.exists()).read_text()) if a.records else records_for(ids)  # --records: the works of the manifest saved earlier (the free API budget is per IP and day)
    recs = [r for r in recs if r.get('type') in core.PAPER_TYPES]
    figures_only = a.stage == 'figures'  # the figure stage: the same works, routes and fetches, no tokenizer, no tables
    tok = None if figures_only else Tokenizer.from_str(http(TOKENIZER, 0.2, 2**28, 120).decode())
    rows = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, row in enumerate(ex.map(lambda r: extract(r, tok, tmp), recs)):
            rows.append(row)
            if i % 200 == 0:
                print(f'{i + 1}/{len(recs)}', flush=True)
    res = {'figures': figure_factors(rows)} if figures_only else encode(rows, tmp, a.rounds, a.seed)
    res['status'] = {k: sum(r['status'] == k for r in rows) for k in sorted({r['status'] for r in rows})}
    res['routes'] = {k: sum(r['route'] == k for r in rows) for k in ('jats', 'pdf', 'unresolved')}
    res['snapshot_deltas'] = snapshot_deltas(a.release, a.previous)
    res['parameters'] = {'tessera_commit': a.tessera_commit, 'seed': a.seed, 'sample_n': len(recs), 'manifest_n': len(man['work_ids']), 'chunk_target': 350, 'tools': tool_versions() | versions(),
                         'min_figure_px': core.MIN_FIGURE_PX, 'extractor': EXTRACTOR}
    (out / ('figures.json' if figures_only else 'tsra.json')).write_text(json.dumps(res, indent=1))
