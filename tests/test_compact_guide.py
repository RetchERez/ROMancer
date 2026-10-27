import unittest

class CompactGuideTests(unittest.TestCase):
    def test_short_topics_share_pages_illustrated_topics_keep_all_visuals_and_wide_fallback_is_explicit(self):
        from tools.compact_guide import layout_groups,figures_for
        rows=[{'id':'one','part':'Basic'},{'id':'two','part':'Basic'},
              {'id':'three','part':'Basic','image_layout':'following-page','visual_page':{'panels':[{'image':'actual','crop':[0,0,100,80]}]}},
              {'id':'four','part':'Advanced'},{'id':'five','part':'Advanced'}]
        groups=layout_groups({'chapters':rows,'compact_wide_topics':[]})
        self.assertEqual([[r['id'] for r in g] for g in groups],[['one','two'],['three'],['four','five']])
        self.assertEqual(figures_for(rows[2])[0]['image'],'actual')
        groups=layout_groups({'chapters':rows,'compact_wide_topics':['one']});self.assertEqual(len(groups),4)
    def test_compact_pagination_maps_integrated_visuals_to_their_actual_topic_page(self):
        from tools.build_user_guide import pagination
        rows=[{'id':'one','part':'Basic','image_layout':'following-page','visual_page':{'panels':[]}},{'id':'two','part':'Advanced'}]
        p,_,_=pagination({'compact_pdf':True,'chapters':rows,'glossary':[],'index':[]})
        self.assertEqual(p['one'],p['one-appearance'])
