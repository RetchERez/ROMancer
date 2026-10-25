import importlib
import unittest


class PlayerDocsTests(unittest.TestCase):
    def test_ordered_line_and_page_controls_keep_text_positions(self):
        from romancer import player_docs as m
        model={'records':[{'annotations':{'speaker_label':'Captain'},'tokens':[
            {'kind':'text','glyphs':[{'text':'HELLO'}]},{'kind':'control','layout_role':'line'},
            {'kind':'text','glyphs':[{'text':'WORLD'}]},{'kind':'control','layout_role':'page'},
            {'kind':'text','glyphs':[{'text':'AGAIN'}]}]}]}
        doc=m.script_document(model,'Harbor')
        self.assertIn('Captain: HELLO\nWORLD\n\nAGAIN\n',m.export_script(doc,'text'))
        html=m.export_script(doc,'html');self.assertIn('HELLO<br>WORLD</p><hr><p>AGAIN',html)

    def test_literal_text_controls_html_escaping_and_no_private_metadata(self):
        try:m=importlib.import_module('romancer.player_docs')
        except ModuleNotFoundError:m=None
        self.assertIsNotNone(m,'player documentation exporter is missing')
        doc={'title':'Harbor <Ω>','lines':[{'speaker':'Captain','text':'Welcome & sail.','controls':['page_break']},
            {'speaker':None,'text':'Choose a course.','controls':['pause']}], 'private_path':'C:/private/game.bin','internal_id':'secret'}
        self.assertEqual(m.export_script(doc,'text'),'Harbor <Ω>\n\nCaptain: Welcome & sail.\n\nUnknown speaker: Choose a course.\n\nBy RetchEWretched\n')
        html=m.export_script(doc,'html');self.assertIn('Harbor &lt;Ω&gt;',html);self.assertIn('Welcome &amp; sail.',html)
        self.assertNotIn('private',html);self.assertNotIn('secret',html)
        walkthrough=m.export_walkthrough({'covered':['harbor'],'unknown_edges':['sea']},{'harbor':'Speak to the captain.','sea':'Sail north.'})
        self.assertIn('Speak to the captain.',walkthrough);self.assertNotIn('Sail north.',walkthrough)
        self.assertIn('Unverified directions: sea',walkthrough);self.assertEqual(m.default_credits(),'By RetchEWretched')
