#!/usr/bin/env python3
"""Rebuild the selected 18-edge publication semantic network.

Python standard library; Inkscape exports vector PDF and a 300-dpi PNG.
Run: python build_publication_graph.py
All documentary provenance is in publication_edge_sources.json/CSV, outside
of the figure. This is a selected view, not the complete knowledge network.
"""
from __future__ import annotations
import argparse, csv, hashlib, html, json, math, os, shutil, struct, subprocess, tempfile, zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
WIDTH, HEIGHT, WIDTH_IN = 1600, 1220, 7
# Each node has one identity and one visible occurrence.
NODES = {
    'kikik': ('Wau Kikik', 650, 590, 230, 86),
    'traditional': ('Traditional\nMalay wau', 650, 100, 260, 92),
    'laga': ('Wau Laga', 1100, 100, 210, 82),
    'powder': ('Powdered glass', 1450, 280, 250, 82),
    'form1': ('Form 1', 260, 300, 170, 76),
    'form2': ('Form 2', 150, 550, 170, 76),
    'form3': ('Form 3', 160, 820, 170, 76),
    'head': ('Head', 100, 120, 140, 70),
    'tail': ('Tail', 85, 400, 130, 70),
    'kaca': ('Wau Kaca', 1130, 420, 210, 76),
    'coated_string': ('Glass-coated\nstring', 1450, 530, 250, 90),
    'laga_heading': ('Laga Kite', 380, 100, 205, 76),
    'melaka': ('Melaka', 1280, 680, 180, 76),
    'eddy': ('Eddy Kite', 1210, 880, 210, 76),
    'paper': ('Wau paper', 950, 1050, 210, 76),
    'leaf': ('Leaf-shaped\nwings', 950, 280, 240, 90),
    'hummer': ('Hummer\n(busur)', 650, 1130, 220, 90),
    'sobek': ('Sobek carving', 330, 1050, 250, 76),
}
# id, subject, object, visible relation, label centre, canonical origin, mapping.
EDGES = [
 ('P01','kikik','traditional','is a',(688,350),'RQ1-N01',1,'direct'),
 ('P02','laga','traditional','is a',(890,75),'RQ1-S01',1,'direct'),
 ('P03','form1','kikik','type of',(420,435),'RQ1-F01',2,'inverse of has_source_described_form'),
 ('P04','form2','kikik','type of',(385,540),'RQ1-F01',3,'inverse of has_source_described_form'),
 ('P05','form3','kikik','type of',(375,725),'RQ1-F01',4,'inverse of has_source_described_form'),
 ('P06','form1','head','has',(150,225),'RQ1-F02',1,'direct'),
 ('P07','form2','tail','has',(150,460),'RQ1-F03',1,'direct; supported subclaim'),
 ('P08','kikik','kaca','also called',(870,465),'RQ1-N03',1,'source-scoped name label'),
 ('P09','kaca','coated_string','named after',(1350,435),'RQ1-N03',2,'display wording for powdered glass on the string'),
 ('P10','kikik','laga_heading','heading name',(470,310),'RQ1-N02',1,'source heading label; no global identity'),
 ('P11','kikik','melaka','official wau of\n(2002)',(985,610),'RQ1-N05',1,'historical source attribution'),
 ('P12','kikik','eddy','resembles',(975,755),'RQ1-C02',1,'direct; not identity'),
 ('P13','kikik','paper','covered with',(880,875),'RQ1-C06',1,'display wording for covering material'),
 ('P14','traditional','leaf','most have',(835,183),'RQ1-S12',1,'non-universal class description'),
 ('P15','kikik','leaf','NOT has',(805,405),'RQ1-C05',1,'explicit negative'),
 ('P16','kikik','hummer','NOT has',(600,900),'RQ1-C03',1,'explicit negative'),
 ('P17','kikik','sobek','NOT has',(430,835),'RQ1-C04',1,'explicit negative'),
 ('P18','laga','powder','string usually\nglazed with',(1320,57),'RQ1-P03',1,'source-scoped practice description; strings, not kite body'),
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_text(path, content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.stem+'_',suffix=path.suffix,dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as f:f.write(content)
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def border(node_id, toward):
    _,x,y,w,h=NODES[node_id];dx,dy=toward[0]-x,toward[1]-y
    scale=1/max(abs(dx)/(w/2),abs(dy)/(h/2))
    return x+dx*scale,y+dy*scale


def edge_points(subject, target, eid):
    if eid=='P18':
        # Orthogonal route keeps the long, qualified relation clear of nodes.
        _,sx,sy,sw,sh=NODES[subject];_,tx,ty,tw,th=NODES[target]
        return [(sx+sw/2,sy),(tx,sy),(tx,ty-th/2)]
    s=NODES[subject];t=NODES[target]
    return [border(subject,(t[1],t[2])),border(target,(s[1],s[2]))]


def text_lines(text,x,y,size=30,weight='normal',edge=False):
    lines=text.split('\n');leading=size*1.18
    start=y-(len(lines)-1)*leading/2+size*.34
    halo=' paint-order="stroke" stroke="white" stroke-width="9" stroke-linejoin="round"' if edge else ''
    return '<text x="%s" y="%s" text-anchor="middle" font-size="%s" font-weight="%s"%s>'%(x,start,size,weight,halo)+''.join('<tspan x="%s" dy="%s">%s</tspan>'%(x,0 if i==0 else leading,html.escape(line)) for i,line in enumerate(lines))+'</text>'


def svg_document():
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH_IN}in" height="{WIDTH_IN*HEIGHT/WIDTH:.6f}in" viewBox="0 0 {WIDTH} {HEIGHT}" role="img">',
       '<title>Selected semantic network for Wau Kikik and Wau Laga</title>',
       '<desc>Eighteen source-scoped relations; one occurrence of each node. Documentary provenance accompanies the figure separately.</desc>',
       '<defs><marker id="arrow" markerUnits="userSpaceOnUse" markerWidth="15" markerHeight="13" refX="14" refY="6.5" orient="auto"><path d="M0,0 L14,6.5 L0,13 Z" fill="black"/></marker></defs>',
       '<rect width="1600" height="1220" fill="white"/>',
       '<g font-family="DejaVu Sans, Arial, sans-serif" fill="black">']
    for eid,source,target,relation,label,rid,index,transformation in EDGES:
        points=edge_points(source,target,eid)
        path='M'+ ' L'.join(f'{x:.3f},{y:.3f}' for x,y in points)
        parts.append(f'<path d="{path}" fill="none" stroke="black" stroke-width="2.7" stroke-linejoin="round" marker-end="url(#arrow)"/>')
    for eid,source,target,relation,(x,y),rid,index,transformation in EDGES:
        parts.append(text_lines(relation,x,y,size=29,weight='bold' if relation.startswith('NOT') else 'normal',edge=True))
    for key,(label,x,y,w,h) in NODES.items():
        parts.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="9" fill="white" stroke="black" stroke-width="{3.2 if key=="kikik" else 2.2}"/>')
        parts.append(text_lines(label,x,y,size=34 if key=='kikik' else 30,weight='bold' if key=='kikik' else 'normal'))
    parts.extend(['</g>','</svg>'])
    return '\n'.join(parts)+'\n'


def check_png(path):
    data=Path(path).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
    pos=8;types=[];compressed=[];dims=None
    while pos<len(data):
        assert pos+12<=len(data),'incomplete PNG chunk'
        size=struct.unpack('>I',data[pos:pos+4])[0];kind=data[pos+4:pos+8];end=pos+size+12
        assert end<=len(data),'truncated PNG chunk'
        payload=data[pos+8:pos+8+size];crc=struct.unpack('>I',data[pos+8+size:end])[0]
        assert zlib.crc32(kind+payload)&0xffffffff==crc,'PNG CRC error'
        types.append(kind)
        if kind==b'IHDR':dims=struct.unpack('>II',payload[:8])
        if kind==b'IDAT':compressed.append(payload)
        pos=end
        if kind==b'IEND':assert size==0;break
    assert types[0]==b'IHDR' and types[-1]==b'IEND' and pos==len(data)
    zlib.decompress(b''.join(compressed))
    return {'width_px':dims[0],'height_px':dims[1],'complete_png':True}


def export_image(svg,kind,inkscape):
    output=svg.with_suffix('.'+kind)
    fd,name=tempfile.mkstemp(prefix=output.stem+'_',suffix='.'+kind,dir=output.parent);os.close(fd)
    temporary=Path(name)
    try:
        cmd=[inkscape,str(svg),'--export-type='+kind,'--export-filename='+str(temporary)]
        if kind=='png':cmd+=['--export-dpi=300','--export-background=white','--export-background-opacity=255']
        subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=120)
        result=check_png(temporary) if kind=='png' else {'pdf_header_valid':temporary.read_bytes().startswith(b'%PDF-')}
        assert all(v for k,v in result.items() if k.endswith('valid'))
        os.replace(temporary,output)
        return {'file':output.name,**result,'sha256':digest(output)}
    finally:temporary.unlink(missing_ok=True)


def connectivity():
    adjacent={node:set() for node in NODES}
    for _,s,t,*_ in EDGES:adjacent[s].add(t);adjacent[t].add(s)
    visited=set();queue=['kikik']
    while queue:
        node=queue.pop()
        if node not in visited:visited.add(node);queue.extend(adjacent[node]-visited)
    assert len(NODES)==18 and len(EDGES)==18 and visited==set(NODES)
    return {'nodes':len(NODES),'edges':len(EDGES),'one_connected_component':True,'no_duplicate_node_occurrences':True}


def source_rows(kb, network):
    operational = {(edge["record_id"], edge["origin"]["triple_index"]): edge for edge in network["edges"]}
    records={r['record_id']:r for r in kb['records']};rows=[]
    for eid,s,t,relation,label,rid,index,transformation in EDGES:
        r=records[rid];triple=r['triples'][index-1]
        canonical_edge = operational[(rid, index)]
        assert canonical_edge['kb_triple'] == triple
        # All selected relations are shown from the English printed source.
        page=144 if rid in ('RQ1-S01','RQ1-P03') else 73
        evidence=[e for e in r['evidence'] if e['page']==page and e['language']=='en']
        assert evidence,(eid,'missing source quote')
        if rid=='RQ1-F01' and index>1:
            related={'P03':'RQ1-F02','P04':'RQ1-F03','P05':'RQ1-F04'}[eid]
            evidence += [e for e in records[related]['evidence'] if e['page']==73 and e['language']=='en']
        related_record = {'P03':'RQ1-F02','P04':'RQ1-F03','P05':'RQ1-F04'}.get(eid)
        related_ids = [rid] + ([related_record] if related_record else [])
        wording = {}
        scope_note = r['limits_en']
        if eid in ('P04','P05'):
            shape_record = records[related_record]
            for st in shape_record['triples']:
                if st['relation']=='has_source_shape_wording':
                    wording['form_wording_ms' if 'Malay' in st['scope'] else 'form_wording_en'] = st['object']
            evidence = r['evidence'] + shape_record['evidence']
            scope_note += ' ' + shape_record['limits_en']
        pages = sorted({e['page'] for e in evidence})
        rows.append({'id':eid,'publication_edge_id':eid,'subject':NODES[s][0].replace('\n',' '),
           'label':relation.replace('\n',' '),'relation':relation.replace('\n',' '),'object':NODES[t][0].replace('\n',' '),
           'record_id':rid,'record_ids':related_ids,'triple_index':index,'canonical_triple':triple,
           'operational_edge_id':canonical_edge['edge_id'],
           'author_decision':canonical_edge.get('author_decision'),
           'pages':pages,'source_pages':pages,'source_id':'S01','evidence':evidence,**wording,
           'display_transformation':transformation,'scope':triple['scope'],
           'scope_note':scope_note,'polarity':triple['polarity'],
           'status':'supported' if rid=='RQ1-F03' and index==1 else r['status']})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--knowledge',type=Path,default=BASE/'knowledge.json')
    parser.add_argument('--output',type=Path,default=BASE/'graphs')
    parser.add_argument('--network',type=Path,default=BASE/'WauTrace_Network_Template.json')
    parser.add_argument('--figure-only',action='store_true',help='Render geometry before the final knowledge mapping is available.')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    graph_checks=connectivity();svg=args.output/'publication_semantic_network.svg'
    atomic_text(svg,svg_document())
    inkscape=shutil.which('inkscape')
    if not inkscape:raise RuntimeError('Install Inkscape and put its executable on PATH for PDF/PNG export.')
    exports=[export_image(svg,'png',inkscape),export_image(svg,'pdf',inkscape)]
    manifest={'selected_view':True,'graph_checks':graph_checks,'width_inches':WIDTH_IN,
       'height_inches':WIDTH_IN*HEIGHT/WIDTH,'png_dpi':300,'exports':exports,
       'script_sha256':digest(__file__),'caption_notes':[
       'Wau Laga and the Laga Kite heading label are separate nodes; no universal identity is asserted.',
       'Most have is a non-universal class-level description. Explicit negative edges concern only the named Kikik features.',
       'The Melaka attribution belongs to the 2002 book.',
       'Kemetek is not documented in the reviewed book passages, so no asserted edge is shown.',
       'Language-specific form-2/form-3 wording belongs in the accompanying evidence table.']}
    if not args.figure_only:
        kb=json.loads(args.knowledge.read_text(encoding='utf-8'))
        network=json.loads(args.network.read_text(encoding='utf-8'))
        assert network['provenance']['knowledge_sha256'] == digest(args.knowledge)
        rows=source_rows(kb, network)
        mapping={'title':'Publication figure: source mapping for the 18 selected edges',
            'knowledge_sha256':digest(args.knowledge),'network_sha256':digest(args.network),'edge_count':len(rows),'edges':rows,
            'author_edge_review':'pending' if any(row['author_decision'] != 'approved' for row in rows) else 'documented',
            'caption_notes':manifest['caption_notes']}
        atomic_text(args.output/'publication_edge_sources.json',json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
        csv_path=args.output/'publication_edge_sources.csv'
        fields=['id','operational_edge_id','subject','label','object','record_ids','pages','quote','form_wording_ms','form_wording_en','scope_note','display_transformation']
        import io
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            out={k:row[k] for k in fields if k in row};out['record_ids']='; '.join(row['record_ids']);out['pages']='; '.join(map(str,row['pages']))
            out['quote']=' | '.join(e['quote'] for e in row['evidence']);writer.writerow(out)
        atomic_text(csv_path,'\ufeff'+stream.getvalue())
        manifest['knowledge_sha256']=digest(args.knowledge);manifest['network_sha256']=digest(args.network);manifest['source_mapping_rows']=len(rows)
        manifest['author_edge_review'] = mapping['author_edge_review']
        manifest['study_ready'] = False
        caption = ('Selected semantic network for Wau Kikik, based on the 2002 source. Laga Kite is retained as a heading name; Wau Laga is represented separately, without asserting universal identity. Most have expresses a non-universal class description and does not override Kikik’s explicit feature exclusions. The Melaka attribution is historical. Kemetek is not established in the reviewed source passages and therefore has no asserted edge. Malay and English descriptions of Forms 2 and 3 are retained in Table 6.1.')
        atomic_text(args.output/'publication_graph_caption.txt', caption+'\n')
    atomic_text(args.output/'publication_graph_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'graph_checks':graph_checks,'exports':exports,'source_mapping_written':not args.figure_only},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
