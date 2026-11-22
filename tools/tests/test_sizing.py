"""Pure parts of the S-013 sizing harness (tools/sizing): projection, JATS text, chunk counting,
statistics and the extrapolation. Synthetic fixtures, no network, stdlib only."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/sizing'))
from sizing import core, run  # noqa: E402

FIX = Path(__file__).parent / 'sizing-fixtures'
PAGE = json.loads((FIX / 'openalex-page.json').read_text())['results']
BULK = {c: {'oa': oa, 'oa_delta': oa * 0.5, 'rest': 0.1} for c, oa in (('low', 0.4), ('central', 0.5), ('high', 0.8))}


def factors(spread=0.2):
    base = {'chunks_350': 40, 'text_zst_bytes': 8e3, 'text_bytes': 30e3, 'meta_parquet_bytes': 600, 'refs': 40,
            'pdf_bytes': 5e5, 'jats_zst_bytes': 2e4, 'pdf_share': 0.4, 'bm25_ratio': 0.35, 'unresolved_share': 0.25,
            # S-015: tessera bytes per paper, figures, and the encoded-to-raw ratio of a vector
            'tsra_meta': 1.5e3, 'tsra_doc': 40e3, 'tsra_text': 20e3, 'jats_share': 0.35, 'fig_blob_jats': 800e3, 'fig_blob_pdf': 300e3, 'figs_jats': 4, 'figs_pdf': 10, 'fig_native_jats': 900e3, 'supp_bytes_jats': 500e3, 'vec_ratio': 0.9, 'vec_int8_ratio': 0.9}
    return {k: {'n': 100, 'mean': v, 'median': v, 'p90': v, 'ci95': [v * (1 - spread), v * (1 + spread)]} for k, v in base.items()}


def figures_doc():
    """The `figures` of a tsra.json that `core.tsra_factors` reads, from the per-route factors of `factors()`."""
    f = factors()
    return {'by_route': {r: {'fig_blob_bytes': f[f'fig_blob_{r}'], 'figs': f[f'figs_{r}'], 'native_bytes': f.get(f'fig_native_{r}', f['fig_blob_pdf'])} for r in ('jats', 'pdf')},
            'supplementary': {'bytes': f['supp_bytes_jats']}}


class Sampling(unittest.TestCase):
    def test_route_follows_cascade_preference(self):
        self.assertEqual([core.route_of(r) for r in PAGE], ['jats', 'pdf', 'unresolved'])
        self.assertEqual(core.pmcid_of(PAGE[0]), 'PMC123')
        self.assertEqual(core.pmcid_of({'ids': {'pmcid': 'https://www.ncbi.nlm.nih.gov/pmc/articles/10022193'}}), 'PMC10022193')

    def test_manifest_counts_sources_and_ids(self):
        m = core.manifest(PAGE, 83, 'f', '2026-11-22', {'article': 2})
        self.assertEqual(m['work_ids'], ['W1', 'W2', 'W3'])
        self.assertEqual(m['per_source_top50'], {'Journal Two': 1, 'PubMed Central': 1, 'unknown': 1})
        self.assertEqual(m['routes'], {'jats': 1, 'pdf': 1, 'unresolved': 1})
        self.assertEqual(json.loads(core.dump_manifest(m)), m)

    def test_projection_keeps_only_hub_fields(self):
        p = core.project(PAGE[0])
        self.assertEqual(p['authorships'], [{'author': 'A1', 'name': 'X', 'institutions': ['I1']}])
        self.assertEqual(p['best_oa_location'], {'license': 'cc-by', 'pdf_url': None, 'landing_page_url': None, 'source': 'S1'})
        self.assertNotIn('abstract_inverted_index', p)

    def test_failed_pdf_fetches_take_the_mean_of_fetched_ones(self):
        rows = [{'route': 'pdf', 'pdf_bytes': 100}, {'route': 'pdf', 'pdf_bytes': 300},
                {'route': 'pdf', 'pdf_bytes': 0}, {'route': 'jats', 'pdf_bytes': 0}]
        self.assertEqual(core.pdf_contributions(rows), [100, 300, 200, 0])


class Text(unittest.TestCase):
    def test_jats_paragraphs_drop_tables_and_references(self):
        self.assertEqual(core.jats_paragraphs((FIX / 'sample.jats.xml').read_bytes()),
                         ['Synthetic abstract about nothing.', 'Introduction', 'First paragraph with a citation inside.', 'Kept figure caption.'])
        self.assertEqual(core.pdf_paragraphs('a  b\nc\n\n\n d\n'), ['a b c', 'd'])

    def test_chunk_packing(self):
        self.assertEqual([core.count_chunks(p, 350) for p in ([], [100] * 3, [200] * 3, [1000])], [0, 1, 3, 3])
        par = [37, 190, 410, 55, 300, 120, 80, 900]
        self.assertGreaterEqual(core.count_chunks(par, 300), core.count_chunks(par, 350))
        self.assertGreaterEqual(core.count_chunks(par, 350), core.count_chunks(par, 400))


class Blocks(unittest.TestCase):
    def test_chunk_packing_returns_the_element_span_of_each_chunk(self):
        self.assertEqual(core.pack_chunks([100, 200, 400, 50], 350), [(0, 1, 300), (2, 2, 350), (2, 3, 100)])
        self.assertEqual(core.pack_chunks([0, 100, 0, 100], 350), [(1, 3, 200)])
        self.assertEqual(core.pack_chunks([], 350), [])
        par = [37, 190, 410, 55, 300, 120, 80, 900]
        for t in (300, 350, 400):
            self.assertEqual(sum(c[2] for c in core.pack_chunks(par, t)), sum(par))  # no token is lost or counted twice
            self.assertEqual(core.count_chunks(par, t), len(core.pack_chunks(par, t)))

    def test_jats_blocks_follow_the_document_model(self):
        b = core.jats_blocks((FIX / 'blocks.jats.xml').read_bytes())
        self.assertEqual([(e['kind'], e['parent'], e['text']) for e in b['elements']],
                         [('paragraph', -1, 'Abstract text.'), ('heading', -1, 'Methods'), ('paragraph', 1, 'We follow Smith and show Figure 1.'),
                          ('heading', 1, 'Detail'), ('paragraph', 3, 'Nested paragraph.'), ('caption', 1, 'Cell counts.')])
        self.assertEqual(b['xrefs'], [(2, 10, 15, 'bibr', 'b1'), (2, 25, 33, 'fig', 'f1')])
        self.assertEqual([(f['id'], f['caption'], f['graphics']) for f in b['figs']], [('f1', 5, ['img-a.jpg', 'img-b.png']), ('f2', -1, ['img-c.jpg'])])
        self.assertEqual([c[:3] + (c[3], c[4] == c[4] and c[4]) for c in b['tables'][2:]], [(0, 1, 0, '1,250.5', 1250.5), (0, 1, 1, '12', 12.0), (0, 2, 0, 'high', False), (0, 2, 1, '\u22123', -3.0)])
        self.assertEqual(b['bib'], [{'id': 'b1', 'title': 'On cells', 'authors': 'Smith; Jones', 'year': '2020', 'doi': '10.1/abc'}])

    def test_the_text_of_the_blocks_is_the_text_the_chunker_counted(self):
        for f in ('sample.jats.xml', 'blocks.jats.xml'):
            x = (FIX / f).read_bytes()
            self.assertEqual(core.jats_paragraphs(x), [e['text'] for e in core.jats_blocks(x)['elements']])

    def test_pdf_layout_survives_control_characters_that_xml_forbids(self):
        # 8 % of the PDFs of the sample made `pdftotext -bbox-layout` emit one: the page was lost, and with it the work's text.
        x = b'<html><doc><page><flow><block xMin="1" yMin="2" xMax="3" yMax="4"><line><word>a\x0cb</word><word>c&#x1;d</word></line></block></flow></page></doc></html>'
        self.assertEqual(core.pdf_layout_blocks(x), [(1, (1.0, 2.0, 3.0, 4.0), 'ab cd')])

    def test_pdf_layout_blocks_carry_page_and_box(self):
        xhtml = (b'<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow>'
                 b'<block xMin="72" yMin="80" xMax="540" yMax="120"><line><word>Hello</word><word>world</word></line></block>'
                 b'<block xMin="1" yMin="2" xMax="3" yMax="4"><line><word></word></line></block></flow></page>'
                 b'<page><flow><block xMin="9" yMin="8" xMax="7" yMax="6"><line><word>Two</word></line></block></flow></page></doc></body></html>')
        self.assertEqual(core.pdf_layout_blocks(xhtml), [(1, (72.0, 80.0, 540.0, 120.0), 'Hello world'), (2, (9.0, 8.0, 7.0, 6.0), 'Two')])


class Figures(unittest.TestCase):
    LIST = ('page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio\n'
            '--------------------------------------------------------------------------------------------\n'
            '   1     0 image     800   600  rgb     3   8  jpeg   no        10  0   150   150 45.2K 3.2%\n'
            '   1     1 smask     800   600  gray    1   8  image  no        10  0   150   150  1.5M 0.1%\n'
            '   2     2 image      32    32  rgb     3   8  flate  no        11  0    72    72  812B 27%\n')

    def test_pdfimages_list_sizes_are_powers_of_1024(self):
        rows = core.parse_pdfimages_list(self.LIST)
        self.assertEqual([(r['page'], r['type'], r['w'], r['enc'], r['bytes']) for r in rows],
                         [(1, 'image', 800, 'jpeg', round(45.2 * 1024)), (1, 'smask', 800, 'image', round(1.5 * 2**20)), (2, 'image', 32, 'flate', 812)])

    def test_a_figure_is_a_real_image_not_a_mask_or_an_icon(self):
        self.assertEqual([core.is_figure(r) for r in core.parse_pdfimages_list(self.LIST)], [True, False, False])


class FigureSelection(unittest.TestCase):
    """The figure term is 89 % of B: what counts as a figure file must be tested. Round 1 counted every file of the PMC folder (53 % of the
    bytes of 44 sampled articles were supplementary material) and every placement of every image of a PDF."""
    FILES = [tuple(f) for f in json.loads((FIX / 'pmc-listing.json').read_text())]
    UNITS = core.jats_blocks((FIX / 'figures.jats.xml').read_bytes())['graphics']

    def test_the_graphic_units_are_the_renditions_of_each_graphic(self):
        self.assertEqual(self.UNITS, [[('art.g001', False), ('art.g001.thumb', True)], [('art.g001', False)], [('art.t001.png', False)]])

    def test_one_rendition_per_graphic_never_a_thumbnail_each_file_once(self):
        # art.g001 exists as jpg and gif: the jpg; the thumbnail and the unreferenced art.g009 are not figures; the table graphic is.
        self.assertEqual(core.pick_graphic_files(self.UNITS, self.FILES), [('art.g001.jpg', 200000), ('art.t001.png', 80000)])

    def test_everything_else_is_supplementary_and_the_jats_pdf_text_are_not(self):
        chosen = core.pick_graphic_files(self.UNITS, self.FILES)
        rest = core.other_files(self.FILES, chosen)
        self.assertEqual(sorted(n for n, _ in rest), ['art.g001.gif', 'art.g001.thumb.jpg', 'art.g009.jpg', 'art.s001.zip', 'art.s002.docx'])
        self.assertEqual(sum(b for _, b in rest), 30000 + 5000 + 70000 + 3000000 + 400000)

    def test_a_pdf_figure_is_an_object_once_and_not_a_mask_a_stencil_or_an_icon(self):
        rows = core.parse_pdfimages_list((FIX / 'pdfimages-list.txt').read_text())
        self.assertEqual(len(rows), 6)  # six placements
        figs = core.figure_images(rows)
        self.assertEqual([(f['page'], f['obj']) for f in figs], [(1, ('10', '0')), (3, ('14', '0'))])
        self.assertEqual(sum(f['bytes'] for f in figs), round(45.2 * 1024) + round(90.0 * 1024))


class Tessera(unittest.TestCase):
    G = {'meta': 100e3, 'doc': 600e3, 'jats': 300e3, 'text': 400e3}

    def test_jats_only_tables_are_spread_over_the_jats_works_and_added_to_every_paper_with_text(self):
        # 100 works, 60 with text, 20 of them JATS: the JATS-only tables (300 KB) are 15 KB per JATS work and every paper with text carries them
        # at that rate (the PDF route needs T1, #84); doc is 600 KB / 60 = 10 KB, text 400 KB / 60.
        p = core.per_paper(self.G, 100, 60, 20)
        self.assertEqual((p['meta'], p['doc'], p['text']), (1e3, 10e3 + 15e3, 400e3 / 60))
        self.assertEqual(core.per_paper(self.G, 100, 60, 0)['doc'], 10e3 + 300e3)  # no JATS work: never a division by zero

    def test_vector_factor_spans_the_encodings_and_the_plan_shape_is_central(self):
        v = {'n': 10, 'vortex_fsl': {'fp16': {'ratio_to_raw': 1.0}, 'int8': {'ratio_to_raw': 0.99}},
             'tessera_array': {'fp16': {'ratio_to_raw': 0.86}, 'int8': {'ratio_to_raw': 0.94}}, 'parquet_zstd': {'fp16': {'ratio_to_raw': 0.94}, 'int8': {'ratio_to_raw': 0.93}}}
        t = {'factors': {'tsra_meta': 1}, 'figures': figures_doc(), 'vectors': {'512': v}}
        f = core.tsra_factors(t)
        self.assertEqual((f['vec_ratio']['mean'], f['vec_ratio']['ci95']), (1.0, [0.86, 1.0]))
        self.assertEqual((f['vec_int8_ratio']['mean'], f['vec_int8_ratio']['ci95']), (0.99, [0.93, 0.99]))
        self.assertEqual((f['tsra_meta'], f['fig_blob_jats'], f['figs_pdf'], f['fig_native_jats'], f['supp_bytes_jats']), (1, factors()['fig_blob_jats'], factors()['figs_pdf'], factors()['fig_native_jats'], factors()['supp_bytes_jats']))


class Snapshots(unittest.TestCase):
    OBJ = [('data/jsonl/works/updated_date=2026-09-22/part_0000.gz', 100), ('data/jsonl/works/updated_date=2026-09-23/part_0000.gz', 10),
           ('data/jsonl/works/updated_date=2026-10-01/part_0000.gz', 20), ('data/jsonl/authors/updated_date=2026-10-13/part_0000.gz', 5),
           ('data/jsonl/works/deleted_ids.csv.gz', 7), ('data/jsonl/works/manifest.json', 1)]

    def test_delta_is_the_partitions_on_or_after_the_previous_release_plus_the_whole_files(self):
        self.assertEqual(core.partition_date(self.OBJ[1][0]), '2026-09-23')
        self.assertIsNone(core.partition_date('data/jsonl/works/deleted_ids.csv.gz'))
        g = core.snapshot_generation(self.OBJ, '2026-09-23')
        self.assertEqual((g['full'], g['delta'], g['whole_each_generation'], g['partitions']), (143, 10 + 20 + 5 + 8, 8, 4))
        self.assertEqual(core.snapshot_generation(self.OBJ, '2026-10-14')['delta'], 8)  # nothing changed since: only the whole files
        self.assertEqual(core.snapshot_generation(self.OBJ, '2000-01-01')['delta'], core.snapshot_generation(self.OBJ, '2000-01-01')['full'])

    def test_bulk_per_case_uses_the_format_of_each_case(self):
        b = core.snapshot_bulk({'jsonl': 8e11, 'parquet': 9e11}, 0.3, {'jsonl': 4e11, 'parquet': 6e11})
        self.assertEqual((b['central']['oa'], b['central']['oa_delta'], b['high']['oa'], b['high']['oa_delta'], b['low']['rest']), (0.8, 0.4, 0.9, 0.6, 0.3))


class Stats(unittest.TestCase):
    def test_summary_is_seeded_and_brackets_the_mean(self):
        s = core.summarize(list(range(1, 101)), rounds=200)
        self.assertEqual((s['n'], s['mean'], s['median']), (100, 50.5, 50.5))
        self.assertAlmostEqual(s['p90'], 90.1)
        self.assertLess(s['ci95'][0], 50.5)
        self.assertGreater(s['ci95'][1], 50.5)
        self.assertEqual(core.summarize([1, 2, 3, 4, 10], 7, 100)['ci95'], core.summarize([1, 2, 3, 4, 10], 7, 100)['ci95'])


class Extrapolation(unittest.TestCase):
    def test_cases_use_ci_bounds(self):
        # Fails if the extrapolation uses the mean for every case: low < central < high must come
        # from the CI bounds of the measured factors, not only from the modelled constants.
        out, flat = core.extrapolate(20e6, factors(), BULK), core.extrapolate(20e6, factors(0.0), BULK)
        for key in ('B', 'R', 'hot_steady', 'warm_peak'):
            self.assertLess(out['low'][key], out['central'][key], key)
            self.assertLess(out['central'][key], out['high'][key], key)
        self.assertGreater(out['high']['vec'], flat['high']['vec'])
        self.assertLess(out['low']['text'], flat['low']['text'])
        self.assertLess(out['low']['idx'], flat['low']['idx'])

    def test_invariants(self):
        a, b = core.extrapolate(10e6, factors(), BULK), core.extrapolate(20e6, factors(), BULK)
        self.assertGreater(b['central']['B'], 1.5 * a['central']['B'])
        for c in core.CASES:
            x = b[c]
            self.assertGreater(x['warm_peak'], x['warm_steady'])
            self.assertGreater(x['hot_peak'], x['hot_steady'])
            self.assertLess(x['hot_steady'], x['warm_steady'])
            self.assertLess(x['hot_peak_int8'], x['hot_peak'])
            self.assertAlmostEqual(sum(x['raw'].values()), x['R'])
        self.assertAlmostEqual(b['central']['vec_int8'] / b['central']['vec'], 516 / 1024, places=6)  # 512 dimensions: 512 bytes and a 4-byte scale against 1,024

    def test_b_is_vectors_tables_and_blobs_with_no_modelled_remainder(self):
        # Every per-paper term of B is measured (S-015): with all of them zero and full coverage only the patent constants are left:
        # the vectors 0.012 TB, the text 0.125 / 3.5 TB and the drawings 1.0 TB. The first model's per-paper remainder is gone.
        z = {k: dict(v, mean=0.0, ci95=[0.0, 0.0]) for k, v in factors(0.0).items()}
        z.update(vec_ratio=factors()['vec_ratio'], vec_int8_ratio=factors()['vec_int8_ratio'], unresolved_share=z['pdf_share'])
        self.assertAlmostEqual(core.extrapolate(10e6, z, BULK)['central']['B'], 0.012 + 0.125 / 3.5 + 1.0, places=9)

    def test_b_adds_each_measured_term_once(self):
        # 20 million papers, 25 % landing page only, 512 dimensions, vectors at 0.9 of raw: every term by hand, in TB. The figure terms
        # follow the population's route shares (35 % JATS, 40 % PDF), not the covered share: 0.35 * 800 KB + 0.4 * 300 KB per paper.
        x, n_cov, n = core.extrapolate(20e6, factors(0.0), BULK)['central'], 15e6, 20e6
        figs = n * (0.35 * 4 + 0.4 * 10)
        self.assertAlmostEqual(x['vec_text'], n_cov * 40 * 512 * 2 * 0.9 / 1e12)
        self.assertAlmostEqual(x['vec_fig'], figs * 512 * 2 * 0.9 / 1e12)
        self.assertAlmostEqual(x['doc'], n_cov * 40e3 / 1e12)
        self.assertAlmostEqual(x['blobs'], n * (0.35 * 800e3 + 0.4 * 300e3) / 1e12)
        self.assertAlmostEqual(x['meta'], n * 1.5e3 / 1e12)
        self.assertAlmostEqual(x['B'], x['vec'] + x['doc'] + x['meta'] + x['blobs'] + 0.125 / 3.5 + 1.0)
        self.assertAlmostEqual(x['text'], n_cov * 20e3 / 1e12 + 0.125 / 3.5)  # the hot text is a column of `doc`, not an extra term
        self.assertAlmostEqual(x['idx_parts']['ivf'], (n_cov * 40 + figs) * 16 / 1e12)

    def test_figures_stored_once_are_counted_once_and_graphics_and_supplements_are_apart(self):
        # #91: one copy of the blobs in the warm tier instead of 2.1 (3.1 at the peak); the JATS graphics as fetched are a raw class of their
        # own, and the supplementary material, not fetched in phase 1, is in no size.
        x = core.extrapolate(20e6, factors(0.0), BULK)['central']
        self.assertAlmostEqual(x['warm_peak'] - x['warm_peak_once'], 2.1 * x['blobs'])
        self.assertAlmostEqual(x['warm_steady'] - x['warm_steady_once'], 1.1 * x['blobs'])
        self.assertAlmostEqual(x['jats_graphics_raw'], 20e6 * 0.35 * 900e3 / 1e12)
        self.assertAlmostEqual(x['supplementary'], 20e6 * 0.35 * 500e3 / 1e12)
        self.assertAlmostEqual(sum(x['raw'].values()), x['R'])  # neither the graphics nor the supplements are in R

    def test_snapshot_class_is_one_generation_plus_deltas(self):
        # R keeps 4 generations of the rest, one full OpenAlex generation and 3 deltas, not 4 full ones.
        raw = core.extrapolate(10e6, factors(), BULK)['central']['raw']['bulk']
        self.assertAlmostEqual(raw, 4 * 0.1 + 0.5 + 3 * 0.25)
        full = {c: dict(g, oa_delta=g['oa']) for c, g in BULK.items()}
        self.assertAlmostEqual(core.extrapolate(10e6, factors(), full)['central']['raw']['bulk'], 4 * 0.1 + 4 * 0.5)

    def test_hot_peak_adds_a_candidate_and_a_second_index_generation(self):
        x = core.extrapolate(20e6, factors(), BULK)['central']
        self.assertAlmostEqual(x['hot_peak'] - x['hot_steady'], x['hot_prod'] + x['idx'])

    def test_patent_parts_are_fixed_and_the_rest_scales_with_the_papers(self):
        # B and R less their patent-scoped constants (and R less the bulk snapshots) are linear in the paper
        # count: that is what lets a stage-0 slice scale the paper part and carry a fixed patent subset.
        one, two = (core.extrapolate(n, factors(), BULK)['central'] for n in (10e6, 20e6))
        self.assertAlmostEqual(two['B'] - two['patent']['b'], 2 * (one['B'] - one['patent']['b']))
        paper_r = lambda x: x['R'] - x['patent']['raw'] - x['raw']['bulk']  # noqa: E731
        self.assertAlmostEqual(paper_r(two), 2 * paper_r(one))
        self.assertEqual(one['patent'], two['patent'])
        self.assertAlmostEqual(one['patent']['b'], 1.0 + 0.012 + 0.125 / 3.5)

    def test_recompute_from_a_measurements_document(self):
        snap = {'openalex_jsonl': {'bytes': 7e11, 'works_records': 4e8, 'entities': {'works': 6e11}}, 'openalex_parquet': {'bytes': 8e11}}
        delta = lambda b: {'2026-07-08': {'delta': b}}  # noqa: E731
        tsra = {'factors': {k: factors()[k] for k in ('tsra_meta', 'tsra_doc', 'tsra_text')}, 'figures': figures_doc(),
                'snapshot_deltas': {'formats': {'jsonl': delta(5e11), 'parquet': delta(6e11)}},
                'vectors': {'512': {'n': 1, **{e: {d: {'ratio_to_raw': 0.9} for d in ('fp16', 'int8')} for e in ('vortex_fsl', 'tessera_array', 'parquet_zstd')}}}}
        doc = {'tsra': tsra, 'population': {'all_types': 4e7, 'papers': 2.3e7, 'article': 2e7}, 'snapshots': snap, 'bases': {b: {'factors': {k: v for k, v in factors().items() if not k.startswith(('tsra', 'fig', 'vec', 'supp'))}} for b in ('all_types', 'papers', 'article')}}
        run.extrapolations(doc)
        self.assertEqual(set(doc['bases']['article']['extrapolation']), set(core.CASES))
        self.assertGreater(doc['bases']['all_types']['extrapolation']['central']['B'], doc['bases']['article']['extrapolation']['central']['B'])
        self.assertLess(doc['model_scope_7M']['central']['B'], doc['bases']['article']['extrapolation']['central']['B'])


if __name__ == '__main__':
    unittest.main()
