"""Dense, readable guide spreads with explicit overflow fallbacks."""
import html,re

def figures_for(row):
    if row.get('image_layout')=='following-page':return row.get('visual_page',{}).get('panels',[])
    result=[{'image':row['image'],'title':row.get('caption','Actual interface'),'caption':''}] if row.get('image') else []
    return result+row.get('extra_images',[])

def layout_groups(data):
    groups=[];pending=None;wide=set(data.get('compact_wide_topics',[]))
    for row in data['chapters']:
        pair=not figures_for(row) and row['id'] not in wide
        if pending:
            if pair and pending['part']==row['part']:groups.append([pending,row]);pending=None;continue
            groups.append([pending]);pending=None
        if pair:pending=row
        else:groups.append([row])
    if pending:groups.append([pending])
    return groups

def topic_blocks(row,titles,terms,pages):
    ink='#143038';muted='#526b72';accent='#14705e'
    values=[(row['intro'],19,ink)]
    values += [(f'<b>{i:02d}</b> '+text,18,ink) for i,text in enumerate(row['steps'],1)]
    values += [('<b>Check the result:</b> '+row['result'],18,ink),('<b>Keep in mind:</b> '+row['note'],17,muted)]
    values += [('<b>'+html.escape(d['title'])+':</b> '+d['text'],17,ink) for d in row.get('details',[])]
    values += [('<b>'+html.escape(n['title'])+':</b> '+n['text'],17,ink) for n in row.get('visual_page',{}).get('notes',[])]
    if row.get('terms'):values.append(('Key terms: '+' / '.join(f'<link href="#{k}" color="{accent}">{html.escape(terms[k])}</link>' for k in row['terms']),14,muted))
    if row.get('related'):values.append(('Related topics: '+', '.join(f'<link href="#{k}" color="{accent}">{pages[k]}</link>' for k in row['related']),14,muted))
    return values

def preflight_layout(data,pages):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    titles={r['id']:r['title'] for r in data['chapters']};terms={r['id']:r['term'] for r in data['glossary']};wide=[]
    for row in data['chapters']:
        width=640;y=927 if figures_for(row) else 850
        for text,size,color in topic_blocks(row,titles,terms,pages):
            text=re.sub(r'<a href="#([^" ]+)">',r'<link href="#\1">',text).replace('</a>','</link>')
            item=Paragraph(text,ParagraphStyle('preflight',fontName='Helvetica',fontSize=size,leading=size*1.36))
            y-=item.wrap(width,3000)[1]+6
        if y<82:wide.append(row['id'])
    return wide

class GuideOverflow(ValueError):
    def __init__(self,topic,message):self.topic=topic;super().__init__(topic+': '+message)

def build_compact_pdf(data,folder,pages,glossary_groups,index_groups,contents_groups):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.lib.utils import ImageReader
    W,H=1440,1080;ink='#143038';muted='#526b72';accent='#14705e';line='#cfddda'
    pdf=canvas.Canvas(str(folder/'guide.pdf'),pagesize=(W,H),invariant=1,pageCompression=1)
    pdf.setTitle('ROMancer v1.0 User Guide - Basic and Advanced');pdf.setAuthor('By RetchEWretched')
    pdf.setSubject('Compact illustrated procedures, original workshop, glossary and index')
    stats=[];active='cover';style=ParagraphStyle('guide',fontName='Helvetica',fontSize=18,leading=24.5,textColor=HexColor(ink),linkUnderline=True)
    titles={r['id']:r['title'] for r in data['chapters']};terms={r['id']:r['term'] for r in data['glossary']}
    def label(text,x,y,size=14,color=muted,bold=False):
        pdf.setFillColor(HexColor(color));pdf.setFont('Helvetica-Bold' if bold else 'Helvetica',size);pdf.drawString(x,y,text)
    def paragraph(text,x,y,width,size=18,color=ink,draw=True):
        text=re.sub(r'<a href="#([^"]+)">',r'<link href="#\1" color="'+accent+'">',text).replace('</a>','</link>')
        item=Paragraph(text,ParagraphStyle('p',parent=style,fontSize=size,leading=size*1.36,textColor=HexColor(color)))
        _,height=item.wrap(width,3000)
        if y-height<82:raise GuideOverflow(active,'text exceeds its readable column')
        if draw:item.drawOn(pdf,x,y-height)
        return y-height
    def frame(title,kicker,anchor):
        pdf.setFillColor(HexColor('#f4f8f6'));pdf.rect(0,0,W,H,fill=1,stroke=0)
        pdf.bookmarkPage(anchor);pdf.addOutlineEntry(title,anchor,level=0,closed=False)
        pdf.setFillColor(HexColor(accent));pdf.rect(48,H-53,40,5,fill=1,stroke=0);label(kicker.upper(),102,H-55,13,accent,True)
        bottom=paragraph(html.escape(title),48,H-86,W-96,31)
        pdf.setStrokeColor(HexColor(line));pdf.line(48,60,W-48,60)
        label('ROMancer v1.0 / By RetchEWretched',48,35,12);label('Back to contents',W-240,35,12,accent)
        pdf.linkRect('','contents',(W-245,23,W-99,51),relative=0,thickness=0);label(str(pdf.getPageNumber()),W-74,35,12,ink,True)
        return bottom-24
    def end(kind):stats.append({'page':pdf.getPageNumber(),'kind':kind});pdf.showPage()
    def blocks(row):return topic_blocks(row,titles,terms,pages)
    def text_column(row,x,y,width,flow=False):
        nonlocal active
        active=row['id'];pdf.bookmarkPage(row['id']);initial_y=y
        for text,size,color in blocks(row):
            try:y=paragraph(text,x,y,width,size,color)-6
            except GuideOverflow:
                if not flow or x>100:raise
                x=750;y=initial_y;y=paragraph(text,x,y,width,size,color)-6
        return y
    def image_panel(panel,x,top,width,height):
        image=ImageReader(str(folder/'screenshots'/(panel['image']+'.png')));iw,ih=image.getSize()
        crop=panel.get('crop',[0,0,iw,ih]);left,upper,cw,ch=crop
        if min(left,upper)<0 or min(cw,ch)<=0 or left+cw>iw or upper+ch>ih:raise ValueError('Screenshot crop lies outside its source')
        factor=min(width/cw,height/ch);dw=cw*factor;dh=ch*factor;bottom=top-dh
        if bottom<83:raise GuideOverflow(active,'illustration exceeds content area')
        pdf.saveState();clip=pdf.beginPath();clip.rect(x,bottom,dw,dh);pdf.clipPath(clip,stroke=0,fill=0)
        pdf.drawImage(image,x-left*factor,bottom-(ih-upper-ch)*factor,width=iw*factor,height=ih*factor)
        pdf.restoreState();pdf.setStrokeColor(HexColor('#b8cec8'));pdf.rect(x,bottom,dw,dh,stroke=1,fill=0)
        return bottom
    active='cover';y=frame('Make a change. Understand it. Test it.','ROMancer / compact user guide','cover')
    y=paragraph(html.escape(data['subtitle']),48,y-15,1280,26)-30
    y=paragraph('NES / SNES / Genesis / Master System / Game Boy / Game Boy Color / GBA',48,y,1280,20,accent)-30
    y=paragraph('<b>Start here</b><br/>Open the editing studio or import a ROM. Check what is ready for that revision. Follow one task through preview, build, test and export.',48,y,1280,23)-30
    y=paragraph(html.escape(data['scope']),48,y,1280,19)-25
    y=paragraph('<b>Use this guide</b><br/>Procedures and illustrations share pages. Short topics share a spread. Every heading, contents entry, glossary term and index page number remains linked. The offline HTML edition includes full-size pictures and topic search.',48,y,1280,21)-30
    paragraph('<link href="#basic" color="'+accent+'">Basic</link> / <link href="#advanced" color="'+accent+'">Advanced</link> / <link href="#glossary" color="'+accent+'">Glossary</link> / <link href="#index" color="'+accent+'">Index</link>',48,y,1280,22)
    paragraph(html.escape(data['attribution']),48,180,1280,14,muted);end('cover')
    for part,index,rows in contents_groups(data):
        active='contents';anchor='contents' if part=='Basic' and index==0 else 'contents-'+part.lower()+('-'+str(index+1) if index else '')
        y=frame(part+' contents'+(' / continued' if index else ''),'Clickable topics and PDF pages',anchor)
        y=paragraph(html.escape(data[part.lower()+'_summary']),48,y,1320,18)-25
        half=(len(rows)+2)//3
        for column in range(3):
            subset=rows[column*half:(column+1)*half];xx=48+column*455;yy=y
            for row in subset:
                text='<link href="#'+row['id']+'" color="'+ink+'">'+html.escape(row['title'])+'</link>'
                end_y=paragraph(text,xx,yy,365,17);label(str(pages[row['id']]),xx+391,yy-17,16,accent,True)
                yy=min(end_y-11,yy-32)
        end('contents')
    wide=set(data.get('compact_wide_topics',[]));firsts={part:next(r['id'] for r in data['chapters'] if r['part']==part) for part in ('Basic','Advanced')}
    for group in layout_groups(data):
        first=group[0];active=first['id']
        if pdf.getPageNumber()!=pages[first['id']]:raise ValueError('Compact PDF pagination differs from contents')
        if len(group)==2:
            y=frame(' / '.join(r['part'] for r in group[:1])+' workflows','Two related procedures',first['id'])
            for column,row in enumerate(group):
                active=row['id'];x=48+column*700;pdf.bookmarkPage(row['id']);pdf.addOutlineEntry(row['title'],row['id'],level=0,closed=False)
                if row['id']==firsts[row['part']]:pdf.bookmarkPage(row['part'].lower())
                yy=paragraph(html.escape(row['title']),x,y,640,25)-15;text_column(row,x,yy,640)
            end('paired:'+first['id']);continue
        row=first;figures=figures_for(row);y=frame(row['title'],row['part']+' / '+row['kicker'],row['id'])
        if row['id']==firsts[row['part']]:pdf.bookmarkPage(row['part'].lower())
        is_wide=row['id'] in wide
        if not figures or is_wide:text_column(row,48,y,640,flow=True)
        else:
            text_column(row,48,y,640)
            if row.get('image_layout')=='following-page':pdf.bookmarkPage(row['id']+'-appearance')
            top=y
            if row.get('visual_page',{}).get('intro'):top=paragraph(row['visual_page']['intro'],720,top,672,15,muted)-12
            gallery_top=top;slot=(top-100)/len(figures)
            for panel in figures:
                heading=panel.get('title','Actual interface')
                top=paragraph(html.escape(heading),720,top,672,16,accent)-10
                caption=panel.get('caption','Full-size picture is available in the offline HTML guide.')
                cap_height=2000-paragraph(html.escape(caption),0,2000,672,14,muted,draw=False)
                image_height=top-(gallery_top-slot*(figures.index(panel)+1))-cap_height-24;bottom=image_panel(panel,720,top,672,max(40,image_height))
                paragraph(html.escape(caption),720,bottom-9,672,14,muted);top=gallery_top-slot*(figures.index(panel)+1)
        end('chapter:'+row['id'])
        if figures and is_wide:
            active=row['id'];top=frame(row.get('visual_page',{}).get('title',row['title']+' / examples'),'Visual reference',row['id']+'-appearance')
            slot=(top-100)/len(figures)
            for i,panel in enumerate(figures):
                yy=top-slot*i;yy=paragraph(html.escape(panel.get('title','Actual interface')),48,yy,1344,18,accent)-10
                caption=panel.get('caption','See the HTML guide for the full-resolution picture.');cap_height=2000-paragraph(html.escape(caption),0,2000,1344,14,muted,draw=False)
                bottom=image_panel(panel,48,yy,1344,max(40,yy-(top-slot*(i+1))-cap_height-24));paragraph(html.escape(caption),48,bottom-9,1344,14,muted)
            end('appearance:'+row['id'])
    for n,group in enumerate(glossary_groups):
        active='glossary';frame('Glossary / '+group[0]['term']+' - '+group[-1]['term'],'Plain-language definitions','glossary' if n==0 else 'glossary-'+str(n+1))
        for col in range(2):
            x=48+col*700;y=905
            for term in group[col*9:(col+1)*9]:
                pdf.bookmarkHorizontalAbsolute(term['id'],y);y=paragraph('<b>'+html.escape(term['term'])+'</b><br/>'+term['definition'],x,y,640,16)-12
        end('glossary')
    all_titles={**titles,**terms,**{r['id']+'-appearance':r['title']+' / examples' for r in data['chapters'] if r.get('image_layout')=='following-page'}}
    for n,group in enumerate(index_groups):
        active='index';frame('Index / '+group[0]['term']+' - '+group[-1]['term'],'Find a topic','index' if n==0 else 'index-'+str(n+1))
        for col in range(2):
            x=48+col*700;y=905
            for item in group[col*27:(col+1)*27]:
                links=', '.join(f'<link href="#{t}" color="{accent}">{pages[t]}</link>' for t in item['topics'])
                y=paragraph('<b>'+html.escape(item['term'])+'</b> '+links,x,y,640,16)-8
        end('index')
    pdf.save();return stats
