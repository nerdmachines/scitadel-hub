"""Pure, stdlib-only parts of the S-013 sizing harness: kept-field projection, JATS text,
chunk counting, statistics and the size-model extrapolation. No network, no third-party code,
so the unit tests run anywhere."""
import json
import math
import random
import re
import statistics
import xml.etree.ElementTree as ET

PAPER_TYPES = ('article', 'review', 'preprint', 'conference-paper')  # scholarly types: the S-014 ruling, the planning case; `type:conference-paper` is OpenAlex's own type
CHUNK_TARGETS = (350, 300, 400)  # tokens: central, then the sensitivity bounds
KEPT = ('id', 'doi', 'title', 'type', 'publication_year', 'publication_date', 'language',
        'authorships', 'primary_topic', 'topics', 'best_oa_location', 'open_access',
        'cited_by_count', 'referenced_works', 'ids')


def project(rec):
    """The OpenAlex fields the hub keeps per work (data-model-and-lifecycle). The abstract is
    left out because its text is counted in the text columns."""
    out = {k: rec.get(k) for k in KEPT}
    out['authorships'] = [{'author': (a.get('author') or {}).get('id'),
                           'name': (a.get('author') or {}).get('display_name'),
                           'institutions': [i.get('id') for i in a.get('institutions') or []]}
                          for a in rec.get('authorships') or []]
    loc = out['best_oa_location'] or {}
    out['best_oa_location'] = {k: loc.get(k) for k in ('license', 'pdf_url', 'landing_page_url')}
    out['best_oa_location']['source'] = (loc.get('source') or {}).get('id')
    return out


def source_of(rec):
    loc = rec.get('best_oa_location') or {}
    src = loc.get('source') or {}
    return src.get('host_organization_name') or src.get('display_name') or 'unknown'


def pmcid_of(rec):
    m = re.search(r'(?:PMC)?(\d+)$', str((rec.get('ids') or {}).get('pmcid') or ''))
    return 'PMC' + m.group(1) if m else None


def route_of(rec):
    """Cascade source preference: JATS where it exists, else a PDF; else unresolved."""
    if pmcid_of(rec):
        return 'jats'
    return 'pdf' if (rec.get('best_oa_location') or {}).get('pdf_url') else 'unresolved'


def manifest(records, seed, flt, date, population):
    per_source = {}
    for r in records:
        per_source[source_of(r)] = per_source.get(source_of(r), 0) + 1
    top = dict(sorted(per_source.items(), key=lambda kv: (-kv[1], kv[0]))[:50])
    routes = {}
    for r in records:
        routes[route_of(r)] = routes.get(route_of(r), 0) + 1
    return {'seed': seed, 'filter': flt, 'date': date, 'population': population,
            'n': len(records), 'routes': routes, 'per_source_top50': top,
            'per_source_other': len(records) - sum(top.values()),
            'work_ids': [r['id'].rsplit('/', 1)[-1] for r in records]}


def dump_manifest(m):
    """One key per line, the work-ID list on a single line (a 10,000-line list diffs badly)."""
    return '{\n' + ',\n'.join(f'{json.dumps(k)}: {json.dumps(v)}' for k, v in m.items()) + '\n}\n'


_SKIP = {'table-wrap', 'table', 'ref-list', 'back', 'inline-formula', 'disp-formula', 'tex-math', 'math'}


def _tag(el):
    return el.tag.rsplit('}', 1)[-1]


_XLINK = '{http://www.w3.org/1999/xlink}href'
_NUM = re.compile(r'[-+\u2212]?\d+(?:\.\d+)?')


def _flat_marks(el, buf, marks):
    """Flat text of an element; records `(start, end, ref-type, rid)` of every xref in the raw text."""
    if _tag(el) in _SKIP:
        return
    buf.append(el.text or '')
    for c in el:
        start = sum(map(len, buf))
        _flat_marks(c, buf, marks)
        if _tag(c) == 'xref':
            marks.append((start, sum(map(len, buf)), c.get('ref-type') or 'other', c.get('rid') or ''))
        buf.append(c.tail or '')


def jats_blocks(xml_bytes):
    """The document-model blocks of a JATS document (document-model.md section 1): `elements` (kind, text, parent:
    the ord of the enclosing section title or -1) of the abstract and body, as the chunker reads them; `xrefs`
    (element ord, span in the raw text, ref-type, rid); `figs` (id, caption element ord or -1, graphic hrefs);
    `tables` (cells: table index, row, col, text, number or NaN); `bib` (parsed fields of each reference)."""
    root = ET.fromstring(xml_bytes)
    els, xrefs, figs = [], [], []

    def emit(kind, el, parent):
        buf, marks = [], []
        _flat_marks(el, buf, marks)
        text = ' '.join(''.join(buf).split())
        if not text:
            return None
        els.append({'kind': kind, 'text': text, 'parent': parent})
        xrefs.extend((len(els) - 1, *m) for m in marks)
        return len(els) - 1

    def walk(el, parent, fig):
        t = _tag(el)
        if t in _SKIP:
            return None
        if t == 'fig':
            fig = {'id': el.get('id') or '', 'caption': -1, 'graphics': [g.get(_XLINK) or '' for g in el.iter() if _tag(g) == 'graphic']}
            figs.append(fig)
        if t in ('p', 'title', 'caption'):
            o = emit({'p': 'paragraph', 'title': 'heading', 'caption': 'caption'}[t], el, parent)
            if o is not None and fig is not None and fig['caption'] < 0:
                fig['caption'] = o
            return o
        cur = parent
        for c in el:
            r = walk(c, cur, fig)
            if t == 'sec' and _tag(c) == 'title' and r is not None:
                cur = r
        return None
    for el in root.iter():
        if _tag(el) in ('abstract', 'body'):
            walk(el, -1, None)

    def text_of(el):
        return ' '.join(''.join(el.itertext()).split()) if el is not None else ''
    cells = []
    for ti, tw in enumerate(e for e in root.iter() if _tag(e) == 'table-wrap'):
        for ri, tr in enumerate(e for e in tw.iter() if _tag(e) == 'tr'):
            for ci, td in enumerate(c for c in tr if _tag(c) in ('td', 'th')):
                x = text_of(td)
                num = x.replace(',', '')
                cells.append((ti, ri, ci, x, float(num.replace('\u2212', '-')) if _NUM.fullmatch(num) else math.nan))
    bib = []
    for ref in (e for e in root.iter() if _tag(e) == 'ref'):
        kids = {_tag(c): c for c in ref.iter()}
        title = next((kids[k] for k in ('article-title', 'chapter-title', 'source') if k in kids), None)  # not `or`: an Element without children is falsy
        doi = next((text_of(c) for c in ref.iter() if _tag(c) == 'pub-id' and c.get('pub-id-type') == 'doi'), '')
        bib.append({'id': ref.get('id') or '', 'title': text_of(title),
                    'authors': '; '.join(text_of(c) for c in ref.iter() if _tag(c) == 'surname')[:200],
                    'year': text_of(kids.get('year')), 'doi': doi})
    return {'elements': els, 'xrefs': xrefs, 'figs': figs, 'tables': cells, 'bib': bib}


def jats_paragraphs(xml_bytes):
    """Abstract and body paragraphs, section titles and figure captions of a JATS document;
    tables, back matter and mathematics are not text for the chunker."""
    return [e['text'] for e in jats_blocks(xml_bytes)['elements']]


def pdf_layout_blocks(xhtml):
    """Text blocks of `pdftotext -bbox-layout` output: `(page, (xmin, ymin, xmax, ymax), text)` per block."""
    out = []
    try:
        root = ET.fromstring(xhtml)
    except ET.ParseError:  # pdftotext passes control characters of the PDF's text through; XML 1.0 does not allow them
        root = ET.fromstring(re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f]|&#(?:x0*[0-9a-fA-F]|x0*1[0-9a-fA-F]|0*[0-9]|0*1[0-9]|0*2[0-9]|0*3[01]);', b'', xhtml))
    for pi, page in enumerate([e for e in root.iter() if _tag(e) == 'page'], 1):
        for blk in (e for e in page.iter() if _tag(e) == 'block'):
            text = ' '.join(w.text or '' for w in blk.iter() if _tag(w) == 'word').strip()
            if text:
                out.append((pi, tuple(float(blk.get(k)) for k in ('xMin', 'yMin', 'xMax', 'yMax')), text))
    return out


def pdf_paragraphs(text):
    return [' '.join(p.split()) for p in re.split(r'\n\s*\n', text) if p.strip()]


def pack_chunks(par_tokens, target):
    """Greedy packing of paragraph token counts into chunks of at most `target` tokens: a paragraph joins the
    open chunk if it fits, otherwise the chunk is flushed; a paragraph longer than the target is split into
    windows of `target`. Returns one `(first_element, last_element, tokens)` per chunk (indices into the list)."""
    chunks, fill, first = [], 0, 0

    def flush(last):
        nonlocal fill
        chunks.append((first, last, fill))
        fill = 0
    for i, n in enumerate(par_tokens):
        if n <= 0:
            continue
        if fill and fill + n > target:
            flush(i - 1)
        if not fill:
            first = i
        while n > target:
            if fill:
                flush(i - 1)
                first = i
            chunks.append((i, i, target))
            n -= target
            first = i
        fill += n
    if fill:
        flush(len(par_tokens) - 1)
    return chunks


def count_chunks(par_tokens, target):
    return len(pack_chunks(par_tokens, target))


_UNITS = {'B': 1, 'K': 2**10, 'M': 2**20, 'G': 2**30}
MIN_FIGURE_PX = 64  # an embedded image counts as a figure (a figure row, a figure vector) if it is an image, not a mask, of at least this side


def parse_pdfimages_list(text):
    """Rows of `pdfimages -list`: page, type (image, mask, smask, stencil), width, height, encoding, embedded bytes
    (the `size` column: K, M, G are powers of 1024)."""
    rows = []
    for line in text.splitlines()[2:]:
        f = line.split()
        if len(f) >= 16:
            m = re.fullmatch(r'([\d.]+)([BKMG]?)', f[14])
            rows.append({'page': int(f[0]), 'type': f[2], 'w': int(f[3]), 'h': int(f[4]), 'enc': f[8],
                         'bytes': round(float(m[1]) * _UNITS[m[2] or 'B']) if m else 0})
    return rows


def is_figure(img):
    return img['type'] == 'image' and min(img['w'], img['h']) >= MIN_FIGURE_PX


def per_paper(group_bytes, n_works, n_text, n_jats):
    """Tessera bytes per paper from the bytes of each table group of a shard: `meta` per work (every work has a row),
    `doc` per work with text, and the JATS-only tables (table cells, inline references, bibliography) per JATS work: PDF-route works need
    the T1 tier for those (#84), so they are modelled at the JATS-route rate (every work with text carries it)."""
    return {'meta': group_bytes['meta'] / n_works, 'doc': group_bytes['doc'] / max(1, n_text) + group_bytes['jats'] / max(1, n_jats),
            'text': group_bytes['text'] / max(1, n_text)}


def partition_date(key):
    m = re.search(r'updated_date=(\d{4}-\d{2}-\d{2})/', key)
    return m[1] if m else None


def snapshot_generation(objects, since):
    """Bytes of one OpenAlex generation and of its delta from the listing `(key, size)` of one snapshot format. Files in an
    `updated_date=` partition changed on or after `since` (the previous release date, ISO) are the delta; files outside any
    partition (deleted_ids, manifests) are whole each generation and count in both."""
    full = sum(sz for _, sz in objects)
    whole = sum(sz for k, sz in objects if partition_date(k) is None)
    changed = sum(sz for k, sz in objects if (partition_date(k) or '') >= since and partition_date(k))
    return {'full': full, 'delta': changed + whole, 'whole_each_generation': whole, 'partitions': len({partition_date(k) for k, _ in objects} - {None})}


def pdf_contributions(rows):
    """PDF bytes per work for the size model: the fetched size for a fetched PDF, the mean fetched
    size for a PDF-route work that could not be fetched (blocked, robots, error), 0 otherwise."""
    got = [r['pdf_bytes'] for r in rows if r['pdf_bytes']]
    mean = sum(got) / len(got) if got else 0
    return [r['pdf_bytes'] or (mean if r['route'] == 'pdf' else 0) for r in rows]


def percentile(values, q):
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def bootstrap_ci(n, stat, seed=83, rounds=1000):
    """95% percentile bootstrap CI of stat(indices) over resamples of range(n) with replacement."""
    rng = random.Random(seed)
    draws = sorted(stat([rng.randrange(n) for _ in range(n)]) for _ in range(rounds))
    return percentile(draws, 0.025), percentile(draws, 0.975)


def summarize(values, seed=83, rounds=1000):
    """n, mean, median, p90 and the bootstrap 95% CI of the mean of a per-item factor."""
    if not values:
        return {'n': 0, 'mean': None, 'median': None, 'p90': None, 'ci95': [None, None]}
    lo, hi = bootstrap_ci(len(values), lambda ix: sum(values[i] for i in ix) / len(ix), seed, rounds)
    return {'n': len(values), 'mean': statistics.fmean(values), 'median': statistics.median(values),
            'p90': percentile(values, 0.9), 'ci95': [lo, hi]}


def at_case(summary, case):
    """The factor value of a case: CI lower bound, mean, CI upper bound."""
    return {'low': summary['ci95'][0], 'central': summary['mean'], 'high': summary['ci95'][1]}[case]


TB = 1e12
CASES = ('low', 'central', 'high')
GENERATIONS = 4  # quarterly bulk-snapshot generations kept (XADR-SCITADEL-008 section 12)
# Modelled values that no measurement has replaced (the patent set, #85; the T1 to T4 cascade, #84; the graph, SYS-019).
MODEL = {'n': {'low': 5e6, 'central': 7e6, 'high': 10e6},
         'text_ratio': 3.5,
         'drawings_b_tb': {'low': 0.5, 'central': 1.0, 'high': 1.5},
         'patent_text_tb': {'low': 0.10, 'central': 0.125, 'high': 0.15},
         'patent_vec_tb': 0.012, 'patent_xml_tb': {'low': 0.05, 'central': 0.1, 'high': 0.15},
         'tei_kb': 4.5, 'raw_drawings_tb': {'low': 0.5, 'central': 1.0, 'high': 2.0},
         't14_mb': {'low': 0.18, 'central': 0.30, 'high': 0.50},
         't14_patent_tb': {'low': 0.1, 'central': 0.2, 'high': 0.5},
         'others_tb': 0.05, 'graph_gb': {'low': 20, 'central': 25, 'high': 30},
         'hnsw_gb': {'low': 0, 'central': 0, 'high': 30}, 'ivf_bytes_per_vec': 16,
         'dims': {'low': 512, 'central': 512, 'high': 1024}, 'delta': 0.1}


def tsra_factors(t):
    """The per-paper factors of `extrapolate` that S-015 measured, from a `tsra.json` document: tessera bytes per paper of the
    metadata, the document-model tables and their text column, the lossless figure bytes and the figure count per covered
    paper, and the encoded-to-raw ratio of a vector (low = the smallest of the encodings measured, central = Vortex's
    fixed_size_list, the shape the plan stores, high = the largest)."""
    f = dict(t['factors'])
    f.update({k: t['figures'][k] for k in ('fig_blob_bytes', 'figs_per_paper')})
    v = t['vectors']['512']
    for name, dt in (('vec_ratio', 'fp16'), ('vec_int8_ratio', 'int8')):
        r = [v[e][dt]['ratio_to_raw'] for e in ('vortex_fsl', 'tessera_array', 'parquet_zstd')]
        f[name] = {'n': v['n'], 'mean': v['vortex_fsl'][dt]['ratio_to_raw'], 'ci95': [min(r), max(r)]}
    return f


def snapshot_bulk(manifest_bytes, rest_tb, delta_bytes):
    """TB of one quarterly OpenAlex generation, of its delta from the previous one, and of the other sources' generation, per case:
    the whole snapshot in jsonl (low, central) or Parquet (high); `rest_tb` (Crossref, DataCite, the unmeasured) is kept whole
    each generation, because its files are yearly and carry no `updated_date` partition."""
    return {c: {'oa': manifest_bytes[fmt] / TB, 'oa_delta': delta_bytes[fmt] / TB, 'rest': rest_tb}
            for c, fmt in (('low', 'jsonl'), ('central', 'jsonl'), ('high', 'parquet'))}


def extrapolate(n_papers, f, bulk):
    """Phase-1 sizes per case from the population count `n_papers` and measured per-paper factors
    `f` (name -> summary; every factor is bytes per paper, zero where it does not apply).
    Case `low`/`high` use the CI bounds, `central` the mean. Sizes in TB (1e12 bytes). `bulk[case]` is the
    `snapshot_bulk` dict: R holds one full OpenAlex generation, `GENERATIONS - 1` deltas and `GENERATIONS` copies of the rest."""
    out = {}
    for c in CASES:
        m = lambda key: MODEL[key][c] if isinstance(MODEL[key], dict) else MODEL[key]  # noqa: E731
        v = lambda name: at_case(f[name], c)  # noqa: E731
        # Works whose only open-access location is a landing page carry metadata only (until #86): text,
        # chunks, vectors and the document tables apply to the covered share; low takes the least coverage.
        cov = 1 - at_case(f['unresolved_share'], {'low': 'high', 'central': 'central', 'high': 'low'}[c])
        n_cov = n_papers * cov
        chunks = n_cov * v('chunks_350')
        figs = n_cov * v('figs_per_paper')
        dims = m('dims')
        vec_text = chunks * dims * 2 * v('vec_ratio') / TB
        vec_fig = figs * dims * 2 * v('vec_ratio') / TB
        vec = vec_text + vec_fig + MODEL['patent_vec_tb']
        patent_text = m('patent_text_tb') / MODEL['text_ratio']
        text = n_cov * v('tsra_text') / TB + patent_text  # the hot chunk text: the text column of the elements block
        meta = n_papers * v('tsra_meta') / TB  # works, authorships and citations blocks
        doc = n_cov * v('tsra_doc') / TB  # elements (text included), chunks, figures, table cells, inline references, bibliography
        blobs = n_cov * v('fig_blob_bytes') / TB  # the figure-blob product: lossless JPEG XL
        b = vec + doc + meta + blobs + patent_text + m('drawings_b_tb')
        bm25 = (n_cov * v('text_bytes') / TB + m('patent_text_tb')) * at_case(f['bm25_ratio'], c)
        ivf = (chunks + figs) * MODEL['ivf_bytes_per_vec'] / TB
        graph_derived = n_papers * v('refs') * 8 / TB  # CSR fwd+rev u32, 8 B per edge
        graph = max(graph_derived, m('graph_gb') / 1e3)  # the modelled whole-graph size is the floor
        idx = bm25 + ivf + graph + m('hnsw_gb') / 1e3
        pdfs = n_papers * v('pdf_share')
        g = bulk[c]
        raw = {'pdf': n_papers * v('pdf_bytes') / TB,
               'xml': n_papers * v('jats_zst_bytes') / TB + pdfs * MODEL['tei_kb'] * 1e3 / TB + m('patent_xml_tb'),
               'bulk': GENERATIONS * g['rest'] + g['oa'] + (GENERATIONS - 1) * g['oa_delta'], 'drawings': m('raw_drawings_tb'),
               't1_t4': pdfs * m('t14_mb') * 1e6 / TB + m('t14_patent_tb')}
        r = sum(raw.values())
        hot_prod = vec + text + meta
        d = MODEL['delta']
        out[c] = {'B': b, 'R': r, 'raw': raw, 'vec': vec, 'vec_text': vec_text, 'vec_fig': vec_fig, 'covered': cov, 'graph_derived': graph_derived, 'text': text, 'meta': meta,
                  'doc': doc, 'blobs': blobs, 'idx': idx,
                  'idx_parts': {'bm25': bm25, 'ivf': ivf, 'graph': graph, 'hnsw': m('hnsw_gb') / 1e3},
                  'products_steady': (2 + d) * b, 'products_peak': (3 + d) * b,
                  'warm_steady': r + (2 + d) * b, 'warm_peak': r + (3 + d) * b,
                  'hot_steady': (1 + d) * hot_prod + idx, 'hot_peak': (2 + d) * hot_prod + 2 * idx,
                  # one byte per dimension and a 4-byte scale per vector, in the measured encoded-to-raw ratio of each dtype
                  'vec_int8': vec * (dims + 4) / (2 * dims) * v('vec_int8_ratio') / v('vec_ratio'), 'hot_prod': hot_prod}
        out[c]['hot_peak_int8'] = out[c]['hot_peak'] - (2 + d) * (vec - out[c]['vec_int8'])
        out[c]['hot_steady_int8'] = out[c]['hot_steady'] - (1 + d) * (vec - out[c]['vec_int8'])
        out[c]['cold'] = r + 6 * b
        # The patent-scoped parts of B, R and the index are modelled constants, not per-paper terms: they do not
        # scale with a slice of the papers, a stage-0 slice carries a fixed patent subset of them (2.4).
        out[c]['patent'] = {'b': m('drawings_b_tb') + MODEL['patent_vec_tb'] + patent_text,
                            'raw': m('patent_xml_tb') + m('raw_drawings_tb') + m('t14_patent_tb'),
                            'idx': m('patent_text_tb') * at_case(f['bm25_ratio'], c)}
    return out
