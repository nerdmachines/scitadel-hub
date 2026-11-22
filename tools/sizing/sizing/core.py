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


def _flat(el):
    if _tag(el) not in _SKIP:
        yield el.text or ''
        for c in el:
            yield from _flat(c)
            yield c.tail or ''


def jats_paragraphs(xml_bytes):
    """Abstract and body paragraphs, section titles and figure captions of a JATS document;
    tables, back matter and mathematics are not text for the chunker."""
    out = []

    def walk(el):
        if _tag(el) in _SKIP:
            return
        if _tag(el) in ('p', 'title', 'caption'):
            text = ' '.join(''.join(_flat(el)).split())
            out.extend([text] if text else [])
            return
        for c in el:
            walk(c)
    for el in ET.fromstring(xml_bytes).iter():
        if _tag(el) in ('abstract', 'body'):
            walk(el)
    return out


def pdf_paragraphs(text):
    return [' '.join(p.split()) for p in re.split(r'\n\s*\n', text) if p.strip()]


def count_chunks(par_tokens, target):
    """Greedy packing of paragraph token counts into chunks of at most `target` tokens: a
    paragraph joins the open chunk if it fits, otherwise the chunk is flushed; a paragraph longer
    than the target is split into windows of `target`. Returns the number of chunks."""
    chunks, fill = 0, 0
    for n in par_tokens:
        if n <= 0:
            continue
        if fill and fill + n > target:
            chunks, fill = chunks + 1, 0
        while n > target:
            if fill:
                chunks, fill = chunks + 1, 0
            chunks, n = chunks + 1, n - target
        fill += n
    return chunks + (1 if fill else 0)


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
# Modelled per-paper residual and per-class values carried over from the first model, scaled to N.
MODEL = {'n': {'low': 5e6, 'central': 7e6, 'high': 10e6},
         'paper_b_tb': {'low': 1.0, 'central': 1.75, 'high': 2.5},
         'vec_kb': 30.0, 'text_raw_kb': 20.0, 'text_ratio': 3.5,
         # 100 million figures over 7 million papers, 512 dimensions in fp16 (1,024 in the high case)
         'figs_per_paper': 14.3, 'fig_vec_kb': {'low': 14.6, 'central': 14.6, 'high': 29.3},
         'drawings_b_tb': {'low': 0.5, 'central': 1.0, 'high': 1.5},
         'patent_text_tb': {'low': 0.10, 'central': 0.125, 'high': 0.15},
         'patent_vec_tb': 0.012, 'patent_xml_tb': {'low': 0.05, 'central': 0.1, 'high': 0.15},
         'tei_kb': 4.5, 'raw_drawings_tb': {'low': 0.5, 'central': 1.0, 'high': 2.0},
         't14_mb': {'low': 0.18, 'central': 0.30, 'high': 0.50},
         't14_patent_tb': {'low': 0.1, 'central': 0.2, 'high': 0.5},
         'others_tb': 0.05, 'graph_gb': {'low': 20, 'central': 25, 'high': 30},
         'hnsw_gb': {'low': 0, 'central': 0, 'high': 30}, 'ivf_bytes_per_vec': 16,
         'dims': {'low': 512, 'central': 512, 'high': 1024}, 'delta': 0.1}


def extrapolate(n_papers, f, bulk_tb):
    """Phase-1 sizes per case from the population count `n_papers` and measured per-paper factors
    `f` (name -> summary; every factor is bytes per paper, zero where it does not apply).
    Case `low`/`high` use the CI bounds, `central` the mean. Sizes in TB (1e12 bytes)."""
    out = {}
    for c in CASES:
        m = lambda key: MODEL[key][c] if isinstance(MODEL[key], dict) else MODEL[key]  # noqa: E731
        v = lambda name: at_case(f[name], c)  # noqa: E731
        # Works whose only open-access location is a landing page carry metadata only (until #86): text,
        # chunks, vectors and the modelled remainder apply to the covered share; low takes the least coverage.
        cov = 1 - at_case(f['unresolved_share'], {'low': 'high', 'central': 'central', 'high': 'low'}[c])
        n_cov = n_papers * cov
        chunks = n_cov * v('chunks_350')
        dims = m('dims')
        vec_text = chunks * dims * 2 / TB
        vec_fig = n_cov * m('fig_vec_kb') * 1e3 / TB
        vec = vec_text + vec_fig + MODEL['patent_vec_tb']
        text = n_cov * v('text_zst_bytes') / TB + m('patent_text_tb') / MODEL['text_ratio']
        meta = n_papers * v('meta_parquet_bytes') / TB
        resid_kb = m('paper_b_tb') * TB / m('n') / 1e3 - MODEL['vec_kb'] - MODEL['text_raw_kb'] / MODEL['text_ratio']
        resid = n_cov * resid_kb * 1e3 / TB
        b = vec + text + meta + resid + m('drawings_b_tb')
        bm25 = (n_cov * v('text_bytes') / TB + m('patent_text_tb')) * at_case(f['bm25_ratio'], c)
        ivf = (chunks + n_cov * MODEL['figs_per_paper']) * MODEL['ivf_bytes_per_vec'] / TB
        graph_derived = n_papers * v('refs') * 8 / TB  # CSR fwd+rev u32, 8 B per edge
        graph = max(graph_derived, m('graph_gb') / 1e3)  # the modelled whole-graph size is the floor
        idx = bm25 + ivf + graph + m('hnsw_gb') / 1e3
        pdfs = n_papers * v('pdf_share')
        raw = {'pdf': n_papers * v('pdf_bytes') / TB,
               'xml': n_papers * v('jats_zst_bytes') / TB + pdfs * MODEL['tei_kb'] * 1e3 / TB + m('patent_xml_tb'),
               'bulk': 4 * bulk_tb[c], 'drawings': m('raw_drawings_tb'),
               't1_t4': pdfs * m('t14_mb') * 1e6 / TB + m('t14_patent_tb')}
        r = sum(raw.values())
        hot_prod = vec + text + meta
        d = MODEL['delta']
        out[c] = {'B': b, 'R': r, 'raw': raw, 'vec': vec, 'vec_text': vec_text, 'vec_fig': vec_fig, 'covered': cov, 'graph_derived': graph_derived, 'text': text, 'meta': meta, 'idx': idx,
                  'idx_parts': {'bm25': bm25, 'ivf': ivf, 'graph': graph, 'hnsw': m('hnsw_gb') / 1e3},
                  'products_steady': (2 + d) * b, 'products_peak': (3 + d) * b,
                  'warm_steady': r + (2 + d) * b, 'warm_peak': r + (3 + d) * b,
                  'hot_steady': (1 + d) * hot_prod + idx, 'hot_peak': (2 + d) * hot_prod + 2 * idx,
                  'vec_int8': vec * (1 + 4 / (2 * dims)) / 2, 'hot_prod': hot_prod}
        out[c]['hot_peak_int8'] = out[c]['hot_peak'] - (2 + d) * (vec - out[c]['vec_int8'])
        out[c]['hot_steady_int8'] = out[c]['hot_steady'] - (1 + d) * (vec - out[c]['vec_int8'])
        out[c]['cold'] = r + 6 * b
    return out
