"""Build ROMancer's offline guide from reviewed JSON and local screenshots.

HTML uses only the standard library. PDF generation additionally needs ReportLab
(a documentation build dependency). Reading the prebuilt guide needs neither.
Run: python tools/build_user_guide.py --guide-dir user-guide
Use --html-only when ReportLab is not installed.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


CSS = """\
:root{color-scheme:light;--ink:#143038;--muted:#526b72;--accent:#14705e;--line:#cfddda;--paper:#f4f8f6}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;color:var(--ink);background:var(--paper);font:18px/1.65 system-ui,Arial,sans-serif}a{color:var(--accent);text-underline-offset:4px}a:focus-visible{outline:3px solid #d59325;outline-offset:5px}nav{position:fixed;inset:0 auto 0 0;width:290px;padding:26px 22px;background:#102329;color:#deeeea;overflow:auto}nav strong{font-size:24px;display:block}nav p{color:#b6cfca;font-size:14px}nav a{display:block;color:#c5e8df;padding:5px 0;font-size:14px;line-height:1.35;text-decoration:none}nav a:hover{text-decoration:underline;color:white}nav h2{font-size:15px;margin:24px 0 9px;color:white}main{margin-left:290px;padding:48px 40px;max-width:2000px}h1{font-size:clamp(36px,4vw,64px);line-height:1.1;max-width:1100px;margin:14px 0 26px}h2{font-size:34px;line-height:1.18;margin:8px 0 24px}h3{font-size:21px;line-height:1.35;margin:28px 0 10px}header{padding-bottom:40px;border-bottom:1px solid var(--line)}.lead{font-size:24px;max-width:1100px}.eyebrow{color:var(--accent);letter-spacing:.12em;font-size:13px;font-weight:750}.pill{display:inline-block;padding:8px 16px;background:#dfebe7;border-radius:6px;text-decoration:none;font-weight:650}.part{padding:34px 0 12px}.part h2{font-size:42px;margin-bottom:8px}.part p{max-width:1000px}.chapter{padding:46px 0;border-bottom:1px solid var(--line)}.intro{max-width:1050px;font-size:20px}.lesson{display:grid;grid-template-columns:minmax(280px,355px) minmax(0,1fr);gap:32px;align-items:start}.lesson.no-image{grid-template-columns:repeat(2,minmax(0,1fr));gap:46px;max-width:1300px}ol{padding-left:26px;margin:12px 0}li{margin-bottom:16px;padding-left:6px}li::marker{color:var(--accent);font-weight:750}aside{background:#e1ede7;border-left:4px solid var(--accent);padding:18px 22px;margin:20px 0}aside p{margin:6px 0}.note,figcaption,.page-ref{color:var(--muted);font-size:15px}figure{margin:20px 0}img{display:block;width:100%;height:auto;border:1px solid #bccfca;border-radius:8px}figcaption{margin-top:10px}.back{display:inline-block;margin-top:22px;font-size:15px}.terms,.index-list,.toc-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 38px}.term{border-bottom:1px solid var(--line);padding:12px 0;scroll-margin-top:26px}dt{font-size:20px;font-weight:700;color:var(--accent)}dd{margin:6px 0 0}.term:target,.chapter:target{outline:2px solid #d5a952;outline-offset:8px}.index-list{list-style:none;padding:0}.index-list li{padding:8px 0;margin:0;border-bottom:1px solid var(--line)}.index-list strong{display:block}.index-list a{font-size:16px}.toc-grid ol{list-style:none;padding:0}.toc-grid li{margin:8px 0;padding:0}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:16px}th,td{padding:12px;border:1px solid var(--line);text-align:left;vertical-align:top}code{font:0.92em ui-monospace,Consolas,monospace;overflow-wrap:anywhere}footer{padding:35px 0;color:var(--muted);font-size:15px;max-width:1200px}.skip{position:absolute;left:-10000px}.skip:focus{position:fixed;top:10px;left:10px;z-index:5;background:white;padding:12px}.related{font-size:15px}@media(max-width:1300px){.lesson{grid-template-columns:1fr}.lesson>div{max-width:1000px}}@media(max-width:850px){nav{position:static;width:auto}nav a{display:inline-block;margin-right:15px}nav h2{margin:16px 0 4px}main{margin:0;padding:28px 20px}.terms,.index-list,.toc-grid,.lesson.no-image{grid-template-columns:1fr}h2{font-size:29px}.lead{font-size:21px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{#guide-search,nav,.back,.skip{display:none}main{margin:0;padding:0}.chapter{break-before:page}a{color:inherit}img{max-height:70vh;object-fit:contain}.lesson,.lesson.no-image{display:block}}
"""


CSS += '''
#guide-search{margin:26px 0;padding:24px;background:#e1e5e9;border:1px solid #b5c0c9;border-radius:8px}#guide-search h2{font-size:26px}#guide-search label{display:block;font-weight:650}.guide-search-controls{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 14px}.guide-search-controls input{flex:1;min-width:180px;background:white;color:#19252d;border:1px solid #788d94;border-radius:6px;padding:12px;font:inherit}.guide-search-controls button{background:#143038;color:white;border:1px solid #143038;border-radius:6px;padding:10px 18px;font:inherit;cursor:pointer}#guide-search :focus-visible{outline:3px solid #9b5e00;outline-offset:3px}#guide-results{margin:0}#guide-results li{margin:16px 0}#guide-results a{font-weight:700}#guide-results p{margin:4px 0;font-size:16px}#guide-search-status{margin:12px 0}
'''

CSS += '.walkthrough-video{max-width:1200px}.walkthrough-video video{display:block;width:100%;aspect-ratio:10/7;background:#10191f;border:1px solid #788d94;border-radius:8px}@media print{.walkthrough-video video{display:none}}'

def load_content(folder):
    data = json.loads((folder / 'guide.json').read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported guide schema')
    seen = {'contents', 'basic', 'advanced', 'glossary', 'index'}
    for row in data['chapters'] + data['glossary']:
        if not re.fullmatch(r'[a-z][a-z0-9-]*', row['id']) or row['id'] in seen:
            raise ValueError('Invalid or duplicate guide anchor: ' + row['id'])
        seen.add(row['id'])
    for chapter in data['chapters']:
        if chapter.get('image_layout') == 'following-page':
            anchor = chapter['id'] + '-appearance'
            if anchor in seen:
                raise ValueError('Duplicate appearance anchor')
            seen.add(anchor)
    for chapter in data['chapters']:
        if chapter['part'] not in ('Basic', 'Advanced'):
            raise ValueError('Every chapter needs a Basic or Advanced part')
        if chapter.get('video'):
            movie=folder/'ROMancer-v1.0.0-Walkthrough.mp4';captions=folder/'walkthrough.en.vtt'
            if chapter['video'] is not True or not movie.is_file() or not captions.is_file():
                raise ValueError('The walkthrough needs its approved local video and captions')
            if not 32<=movie.stat().st_size<=16*1024*1024 or captions.stat().st_size>128*1024:
                raise ValueError('Walkthrough media exceeds the guide budget')
            with movie.open('rb') as stream:signature=stream.read(12)
            if signature[4:8]!=b'ftyp' or not captions.read_text(encoding='utf-8').startswith('WEBVTT\n'):
                raise ValueError('Walkthrough media has an unexpected format')
        if chapter.get('image'):
            image = chapter['image']
            if not re.fullmatch(r'[a-z0-9-]+', image):
                raise ValueError('Unsafe screenshot name')
            if not (folder / 'screenshots' / (image + '.png')).is_file():
                raise ValueError('Missing screenshot: ' + image)
        for extra in chapter.get('extra_images', []):
            if not re.fullmatch(r'[a-z0-9-]+', extra['image']) or not (folder / 'screenshots' / (extra['image'] + '.png')).is_file():
                raise ValueError('Invalid supplementary screenshot')
        for related in chapter.get('related', []):
            if related not in seen:
                raise ValueError('Unknown related topic: ' + related)
        if any(term not in seen for term in chapter.get('terms', [])):
            raise ValueError('Unknown glossary term in ' + chapter['id'])
    for item in data['index']:
        if any(topic not in seen for topic in item['topics']):
            raise ValueError('Unknown index topic: ' + item['term'])
    return data


def chunks(rows, count):
    return [rows[start:start + count] for start in range(0, len(rows), count)]


def contents_groups(data):
    return [(part,index,group) for part in ('Basic','Advanced')
            for index,group in enumerate(chunks([row for row in data['chapters'] if row['part']==part],48 if data.get('compact_pdf') else 21))]


def pagination(data):
    # Cover, bounded contents pages, procedures and visual continuations.
    pages = {}
    next_page = 2+len(contents_groups(data))
    if data.get('compact_pdf'):
        from tools.compact_guide import layout_groups,figures_for
        for group in layout_groups(data):
            for chapter in group:
                pages[chapter['id']]=next_page
                if chapter.get('image_layout')=='following-page':pages[chapter['id']+'-appearance']=next_page+(1 if chapter['id'] in data.get('compact_wide_topics',[]) else 0)
            next_page+=1
            if len(group)==1 and group[0]['id'] in data.get('compact_wide_topics',[]) and figures_for(group[0]):next_page+=1
    else:
        for chapter in data['chapters']:
            pages[chapter['id']] = next_page
            next_page += 1
            if chapter.get('image_layout') == 'following-page':
                pages[chapter['id'] + '-appearance'] = next_page
                next_page += 1
    terms = sorted(data['glossary'], key=lambda row: row['term'].casefold())
    glossary_groups = chunks(terms, 18)
    pages['glossary'] = next_page
    for group in glossary_groups:
        for term in group:
            pages[term['id']] = next_page
        next_page += 1
    index_groups = chunks(sorted(data['index'], key=lambda row: row['term'].casefold()), 54)
    pages['index'] = next_page
    pages['contents'] = 2
    for part in ('Basic', 'Advanced'):
        pages[part.lower()] = pages[next(row['id'] for row in data['chapters'] if row['part'] == part)]
    return pages, glossary_groups, index_groups


def build_html(data, folder, pages):
    esc = html.escape
    titles = {row['id']: row['title'] for row in data['chapters']}
    titles.update({row['id'] + '-appearance': row['title'] + ' / examples' for row in data['chapters'] if row.get('image_layout') == 'following-page'})
    titles.update({row['id']: row['term'] for row in data['glossary']})
    titles.update({'glossary': 'Glossary', 'index': 'Alphabetical index'})
    navigation = []
    toc = []
    sections = []
    for part, summary in [('Basic', data['basic_summary']), ('Advanced', data['advanced_summary'])]:
        rows = [row for row in data['chapters'] if row['part'] == part]
        links = ''.join(f'<li><a href="#{row["id"]}">{esc(row["title"])}</a> <span class="page-ref">PDF {pages[row["id"]]}</span></li>' for row in rows)
        toc.append(f'<div><h3>{part}</h3><ol>{links}</ol></div>')
        navigation.append(f'<h2><a href="#{part.lower()}">{part}</a></h2>' + ''.join(f'<a href="#{row["id"]}">{esc(row["title"])}</a>' for row in rows))
        sections.append(f'<div class="part" id="{part.lower()}"><p class="eyebrow">{part.upper()}</p><h2>{part} workflows</h2><p>{esc(summary)}</p></div>')
        for row in rows:
            movie=''
            if row.get('video'):
                movie='<figure class="walkthrough-video"><video controls playsinline preload="none" poster="screenshots/38-sprite-preview.png" aria-label="Original NES workshop editing walkthrough"><source src="ROMancer-v1.0.0-Walkthrough.mp4" type="video/mp4"><track kind="captions" src="walkthrough.en.vtt" srclang="en" label="English"><p>Open ROMancer-v1.0.0-Walkthrough.mp4 in a local video player.</p></video><figcaption>Actual application recording with instructional captions and a pointer highlight. <a href="ROMancer-v1.0.0-Walkthrough.mp4" download>Download MP4</a> · <a href="walkthrough.en.vtt" download>English captions</a>. The steps below are the text alternative.</figcaption></figure>'
            steps = ''.join('<li>' + text + '</li>' for text in row['steps'])
            details = ''.join(f'<h3>{esc(block["title"])}</h3><p>{block["text"]}</p>' for block in row.get('details', []))
            result = '<aside><b>Check the result</b><p>' + row['result'] + '</p></aside>'
            note = '<p class="note"><b>Keep in mind.</b> ' + row['note'] + '</p>'
            figure = ''
            if row.get('image'):
                image = f'screenshots/{row["image"]}.png'
                figure = f'<figure><a href="{image}" target="_blank" rel="noopener"><img src="{image}" width="1600" height="1000" loading="lazy" alt="{esc(row.get("image_alt", row["title"]), quote=True)}"></a><figcaption>{esc(row.get("caption", "Actual ROMancer interface. Open the image for full resolution."))}</figcaption></figure>'
                if row.get('image_layout') == 'following-page':
                    figure = '<div id="' + row['id'] + '-appearance">' + figure
                    for extra in row.get('extra_images', []):
                        src = 'screenshots/' + extra['image'] + '.png'
                        figure += f'<figure><a href="{src}" target="_blank" rel="noopener"><img src="{src}" width="1600" height="1000" loading="lazy" alt="{esc(extra["title"], quote=True)}"></a><figcaption>{esc(extra["title"])}. Open for the full-resolution example.</figcaption></figure>'
                    for note in row.get('visual_page', {}).get('notes', []):
                        figure += f'<h3>{esc(note["title"])}</h3><p>{note["text"]}</p>'
                    figure += '</div>'
            related = ' | '.join(f'<a href="#{topic}">{esc(titles[topic])}</a>' for topic in row.get('related', []))
            term_links = ' | '.join(f'<a href="#{topic}">{esc(titles[topic])}</a>' for topic in row.get('terms', []))
            sections.append(f'<section class="chapter" id="{row["id"]}"><p class="eyebrow">{part.upper()} / {esc(row["kicker"])}</p><h2>{esc(row["title"])}</h2><p class="intro">{row["intro"]}</p>{movie}<div class="lesson{ "" if figure else " no-image"}"><div><h3>Do this</h3><ol>{steps}</ol>{note}</div><div>{figure}{result}{details}</div></div><p class="related">Key terms: {term_links}</p><p class="related">Related: {related}</p><a class="back" href="#contents">Back to contents</a> <span class="page-ref">PDF page {pages[row["id"]]}</span></section>')
    terms = ''.join(f'<div class="term" id="{row["id"]}"><dt>{esc(row["term"])}</dt><dd>{row["definition"]}</dd></div>' for row in sorted(data['glossary'], key=lambda row: row['term'].casefold()))
    index = ''.join('<li><strong>' + esc(row['term']) + '</strong>' + ' | '.join(f'<a href="#{topic}">{esc(titles[topic])} <span class="page-ref">(PDF {pages[topic]})</span></a>' for topic in row['topics']) + '</li>' for row in sorted(data['index'], key=lambda row: row['term'].casefold()))
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(data['product'])} User Guide</title><link rel="stylesheet" href="guide.css"><script src="guide.js" defer></script></head>
<body><a class="skip" href="#contents">Skip to guide contents</a><nav aria-label="Guide contents"><strong>{esc(data['product'])}</strong><p>By RetchEWretched</p><a href="#guide-search">Search guide</a><a href="#contents">Contents</a>{''.join(navigation)}<h2>Reference</h2><a href="#glossary">Glossary</a><a href="#index">Alphabetical index</a><a href="guide.pdf">PDF edition</a></nav><main><header id="contents"><p class="eyebrow">OFFLINE USER GUIDE / BASIC + ADVANCED</p><h1>Make a change.<br>Understand it. Test it.</h1><p class="lead">{esc(data['subtitle'])}</p><p>NES / SNES / Genesis / Master System / Game Boy / Game Boy Color</p><p><a class="pill" href="#basic">Start with Basic</a> <a class="pill" href="#advanced">Advanced workflows</a> <a class="pill" href="#glossary">Glossary</a> <a class="pill" href="#index">Index</a></p><p>{esc(data['scope'])}</p><section id="guide-search" aria-labelledby="guide-search-title"><h2 id="guide-search-title">Find help</h2><form id="guide-search-form"><label for="guide-query">Search topics, tools or terms</label><div class="guide-search-controls"><input id="guide-query" type="search" maxlength="200" placeholder="Try palette, save states or undo" autocomplete="off"><button type="submit">Search</button><button type="button" id="guide-search-clear">Clear</button></div></form><p class="note">Works offline. For an exact phrase on this page, use your browser’s Find command.</p><p id="guide-search-status" role="status" aria-live="polite"></p><ol id="guide-results"></ol><noscript><p>Enable JavaScript for topic search, or use the contents, glossary and index below.</p></noscript></section><div class="toc-grid">{''.join(toc)}</div><p><a href="#glossary">Glossary</a> (PDF {pages['glossary']}) | <a href="#index">Alphabetical index</a> (PDF {pages['index']}) | <a href="guide.pdf">Download PDF</a></p></header>{''.join(sections)}<section class="chapter" id="glossary"><p class="eyebrow">REFERENCE / A-Z</p><h2>Glossary</h2><dl class="terms">{terms}</dl><a class="back" href="#contents">Back to contents</a></section><section class="chapter" id="index"><p class="eyebrow">REFERENCE / FIND A TOPIC</p><h2>Alphabetical index</h2><p>Links open the relevant topic. Page numbers refer to the bundled PDF edition.</p><ul class="index-list">{index}</ul><a class="back" href="#contents">Back to contents</a></section><footer>{esc(data['attribution'])}</footer></main></body></html>
'''
    ids = re.findall(r'\bid="([^"]+)"', page)
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate HTML anchors')
    for target in re.findall(r'href="#([^"]+)"', page):
        if target not in ids:
            raise ValueError('Broken HTML fragment: ' + target)
    (folder / 'guide.css').write_text(CSS, encoding='utf-8', newline='\n')
    (folder / 'index.html').write_text(page, encoding='utf-8', newline='\n')


def build_pdf(data, folder, pages, glossary_groups, index_groups):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph
        from reportlab.lib.utils import ImageReader
    except ImportError as exc:
        raise SystemExit('PDF builds need ReportLab. Install it in your documentation environment, or pass --html-only. The prebuilt guide.pdf remains usable.') from exc

    width, height = 1440, 1080
    ink, muted, accent, paper, line = '#143038', '#526b72', '#14705e', '#f4f8f6', '#cfddda'
    pdf = canvas.Canvas(str(folder / 'guide.pdf'), pagesize=(width, height), invariant=1, pageCompression=1)
    pdf.setTitle(data['product'] + ' User Guide - Basic and Advanced')
    pdf.setAuthor('By RetchEWretched')
    pdf.setSubject('Offline procedures, actual interface examples, glossary and alphabetical index')
    body = ParagraphStyle('body', fontName='Helvetica', fontSize=18, leading=26, textColor=HexColor(ink))
    stats = []
    term_titles = {row['id']: row['term'] for row in data['glossary']}

    def para(text, x, y, column_width, size=18, color=ink):
        # Body content uses the same small markup vocabulary in both editions.
        from tools.compact_guide import pdf_links
        text = pdf_links(text,accent)
        style = ParagraphStyle('p', parent=body, fontSize=size, leading=size * 1.42, textColor=HexColor(color), linkUnderline=True)
        item = Paragraph(text, style)
        _, used = item.wrap(column_width, 2000)
        if y - used < 77:
            raise ValueError(f'Content overflows PDF page {pdf.getPageNumber()}: {text[:100]}')
        item.drawOn(pdf, x, y - used)
        return y - used

    def label(text, x, y, size=13, color=muted, bold=False):
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        pdf.setFillColor(HexColor(color))
        pdf.drawString(x, y, text)

    def frame(title, kicker, anchor, level=0):
        pdf.setFillColor(HexColor(paper)); pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.bookmarkPage(anchor); pdf.addOutlineEntry(title, anchor, level=level, closed=False)
        pdf.setFillColor(HexColor(accent)); pdf.rect(48, height - 53, 40, 5, fill=1, stroke=0)
        label(kicker.upper(), 102, height - 55, 13, accent, True)
        title_bottom = para(html.escape(title), 48, height - 86, width - 96, 36)
        pdf.setStrokeColor(HexColor(line)); pdf.line(48, 60, width - 48, 60)
        label(data['product'] + ' / By RetchEWretched', 48, 35, 12)
        pdf.linkRect('', 'contents', (width - 240, 23, width - 103, 51), relative=0, thickness=0)
        label('Back to contents', width - 240, 35, 12, accent)
        label(str(pdf.getPageNumber()), width - 74, 35, 12, ink, True)
        return title_bottom - 25

    def end(kind):
        stats.append({'page': pdf.getPageNumber(), 'kind': kind})
        pdf.showPage()

    y = frame(data['product'], 'User guide / Basic + Advanced', 'cover')
    y = para('Make a change.<br/>Understand it. Test it.', 48, y - 45, 1170, 68)
    y = para(html.escape(data['subtitle']), 52, y - 42, 1120, 27)
    y = para('NES / SNES / Genesis / Master System / Game Boy / Game Boy Color', 52, y - 38, 1160, 20, accent)
    y = para('<link href="#basic" color="' + accent + '"><b>Basic workflows</b></link>  /  <link href="#advanced" color="' + accent + '"><b>Advanced workflows</b></link>  /  <link href="#glossary" color="' + accent + '"><b>Glossary</b></link>  /  <link href="#index" color="' + accent + '"><b>Index</b></link>', 52, y - 35, 1200, 21)
    y = para(html.escape(data['scope']), 52, y - 35, 1100, 18)
    para(html.escape(data['attribution']), 52, 220, 1250, 14, muted)
    end('cover')

    for part,group_index,rows in contents_groups(data):
        anchor='contents' if part=='Basic' and group_index==0 else 'contents-'+part.lower()+('-'+str(group_index+1) if group_index else '')
        y = frame(part + ' contents'+(' / continued' if group_index else ''), 'Contents / clickable topics and page numbers', anchor)
        y = para(html.escape(data[part.lower() + '_summary']), 48, y, 1200, 19) - 28
        row_gap=min(35,(y-185)/max(1,len(rows)))
        if row_gap<29:raise ValueError('Contents requires another page; do not overlap reference links')
        for row in rows:
            number = pages[row['id']]
            pdf.linkRect('', row['id'], (48, y - 23, width - 48, y + 7), relative=0, thickness=0)
            label(row['title'], 54, y - 13, 20, ink)
            pdf.setFont('Helvetica-Bold', 17); pdf.setFillColor(HexColor(accent)); pdf.drawRightString(width - 61, y - 13, str(number))
            pdf.setStrokeColor(HexColor(line)); pdf.line(48, y - 28, width - 48, y - 28)
            y -= row_gap
        para(f'<link href="#glossary" color="{accent}">Glossary, page {pages["glossary"]}</link>  /  <link href="#index" color="{accent}">Alphabetical index, page {pages["index"]}</link>', 54, 130, 1180, 18)
        end('contents')

    for row in data['chapters']:
        if pdf.getPageNumber() != pages[row['id']]:
            raise ValueError('PDF pagination changed unexpectedly')
        y = frame(row['title'], row['part'] + ' / ' + row['kicker'], row['id'])
        if row['id'] == next(ch['id'] for ch in data['chapters'] if ch['part'] == row['part']):
            pdf.bookmarkPage(row['part'].lower())
        y = para(row['intro'], 48, y, 1320, 20) - 24
        has_image = bool(row.get('image')) and row.get('image_layout') != 'following-page'
        left_width = 310 if has_image else 630
        right_x = 392 if has_image else 750
        right_width = 1000 if has_image else 640
        left_y = y
        label('DO THIS', 48, left_y - 2, 13, accent, True); left_y -= 27
        for n, step in enumerate(row['steps'], 1):
            left_y = para(f'<b>{n:02d}</b>  ' + step, 48, left_y, left_width, 17 if has_image else 19) - 17
        left_y = para('<b>Keep in mind</b><br/>' + row['note'], 48, left_y - 4, left_width, 15 if has_image else 17, muted)
        right_y = y
        if has_image:
            image = ImageReader(str(folder / 'screenshots' / (row['image'] + '.png')))
            iw, ih = image.getSize()
            image_height = right_width * ih / iw
            if image_height > 625:
                image_height = 625
            bottom = right_y - image_height
            if bottom < 160:
                image_height = right_y - 160; right_width = image_height * iw / ih
                bottom = 160
            pdf.setFillColor(HexColor('#ffffff')); pdf.rect(right_x - 1, bottom - 1, right_width + 2, image_height + 2, fill=1, stroke=0)
            pdf.drawImage(image, right_x, bottom, width=right_width, height=image_height, preserveAspectRatio=True)
            pdf.setStrokeColor(HexColor('#b8cec8')); pdf.rect(right_x, bottom, right_width, image_height, fill=0, stroke=1)
            right_y = para(html.escape(row.get('caption', 'Actual interface capture. Open the HTML edition for the full-resolution screenshot.')), right_x, bottom - 12, right_width, 13, muted) - 15
        right_y = para('<b>Check the result</b><br/>' + row['result'], right_x, right_y, right_width, 16 if has_image else 20) - 22
        for block in row.get('details', []):
            right_y = para('<b>' + html.escape(block['title']) + '</b><br/>' + block['text'], right_x, right_y, right_width, 15 if has_image else 18) - 20
        terms = ' / '.join(f'<link href="#{key}" color="{accent}">{html.escape(term_titles[key])}</link>' for key in row.get('terms', []))
        para('Key terms: ' + terms, 48, 105, 1310, 14, muted)
        end('chapter:' + row['id'])
        if row.get('image_layout') == 'following-page':
            visual = row['visual_page']
            frame(visual['title'], visual['kicker'], row['id'] + '-appearance')
            para(visual['intro'], 48, 922, 1320, 19)

            def screenshot_detail(name, x, top, display_width, crop):
                # Show a detail of an actual capture without redrawing content.
                # The unaltered full-resolution image remains linked in HTML.
                image = ImageReader(str(folder / 'screenshots' / (name + '.png')))
                iw, ih = image.getSize()
                crop_left, crop_top, crop_width, crop_height = crop
                if (min(crop_left, crop_top) < 0 or min(crop_width, crop_height) <= 0
                        or crop_left + crop_width > iw or crop_top + crop_height > ih):
                    raise ValueError('Screenshot detail lies outside its source capture')
                factor = display_width / crop_width
                display_height = crop_height * factor
                bottom = top - display_height
                if bottom < 65 or x < 0 or x + display_width > width:
                    raise ValueError('Screenshot detail lies outside the PDF content area')
                pdf.saveState()
                clip = pdf.beginPath(); clip.rect(x, bottom, display_width, display_height)
                pdf.clipPath(clip, stroke=0, fill=0)
                pdf.drawImage(image, x - crop_left * factor, bottom - (ih - crop_top - crop_height) * factor, width=iw * factor, height=ih * factor)
                pdf.restoreState()
                pdf.setStrokeColor(HexColor('#b8cec8')); pdf.rect(x, bottom, display_width, display_height, fill=0, stroke=1)
                return bottom

            for panel in visual['panels']:
                label(panel['title'], panel['x'], panel['top'] + 23, 17, accent, True)
                bottom = screenshot_detail(panel['image'], panel['x'], panel['top'], panel['width'], panel['crop'])
                if panel.get('caption'):
                    para(panel['caption'], panel['x'], bottom - 12, panel['width'], 13, muted)
            for note in visual.get('notes', []):
                para('<b>' + html.escape(note['title']) + '</b><br/>' + note['text'], note['x'], note['y'], note['width'], 19)
            end('appearance:' + row['id'])

    for group_n, group in enumerate(glossary_groups):
        frame('Glossary / ' + group[0]['term'] + ' - ' + group[-1]['term'], 'Reference / plain language definitions', 'glossary' if not group_n else 'glossary-' + str(group_n + 1))
        for column, subset in enumerate(chunks(group, 9)):
            x = 48 + column * 700; y = height - 175
            for term in subset:
                pdf.bookmarkHorizontalAbsolute(term['id'], y)
                y = para('<b>' + html.escape(term['term']) + '</b><br/>' + term['definition'], x, y, 635, 16) - 12
        end('glossary')

    titles = {row['id']: row['title'] for row in data['chapters']}
    titles.update({row['id'] + '-appearance': row['title'] + ' / examples' for row in data['chapters'] if row.get('image_layout') == 'following-page'})
    titles.update({row['id']: row['term'] for row in data['glossary']})
    for group_n, group in enumerate(index_groups):
        frame('Alphabetical index / ' + group[0]['term'] + ' - ' + group[-1]['term'], 'Reference / topic links and PDF pages', 'index' if not group_n else 'index-' + str(group_n + 1))
        for column, subset in enumerate(chunks(group, 27)):
            x = 48 + column * 700; y = height - 170
            for item in subset:
                links = ', '.join(f'<link href="#{topic}" color="{accent}">{pages[topic]}</link>' for topic in item['topics'])
                y = para('<b>' + html.escape(item['term']) + '</b>  ' + links, x, y, 635, 16) - 8
        end('index')
    pdf.save()
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guide-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'user-guide')
    parser.add_argument('--html-only', action='store_true', help='Build HTML/CSS without importing PDF dependencies')
    args = parser.parse_args()
    folder = args.guide_dir.resolve()
    data = load_content(folder)
    pages, glossary_groups, index_groups = pagination(data)
    stats=[]
    if not args.html_only:
        if data.get('compact_pdf'):
            from tools.compact_guide import build_compact_pdf,GuideOverflow,preflight_layout
            data['compact_wide_topics']=sorted(set(data.get('compact_wide_topics',[]))|set(preflight_layout(data,pages)))
            pages,glossary_groups,index_groups=pagination(data)
            for attempt in range(len(data['chapters'])+1):
                try:stats=build_compact_pdf(data,folder,pages,glossary_groups,index_groups,contents_groups);break
                except GuideOverflow as error:
                    if error.topic in data.get('compact_wide_topics',[]) or error.topic not in {r['id'] for r in data['chapters']}:raise
                    data.setdefault('compact_wide_topics',[]).append(error.topic)
                    pages,glossary_groups,index_groups=pagination(data)
            else:raise ValueError('Guide layout could not be resolved without shrinking text.')
            (folder/'guide.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
        else:stats=build_pdf(data, folder, pages, glossary_groups, index_groups)
    build_html(data, folder, pages)
    print(json.dumps({'ok': True, 'chapters': len(data['chapters']), 'screenshots': sum(bool(row.get('image')) + len(row.get('extra_images', [])) for row in data['chapters']), 'glossary_terms': len(data['glossary']), 'index_entries': len(data['index']), 'pdf_pages': len(stats), 'html_only': args.html_only}))


if __name__ == '__main__':
    main()
