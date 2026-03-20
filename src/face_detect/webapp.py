"""Live web dashboard for face detection results — serves on port 64531."""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, send_file, send_from_directory, request, render_template_string

from .config import load_config
from .database import Database

log = logging.getLogger(__name__)


def extract_date_from_path(file_path: str) -> str:
    """Try to extract a date from the file path or name."""
    name = Path(file_path).stem
    m = re.search(r'(20[012]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'(20[012]\d)[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])', name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    parts = Path(file_path).parts
    for part in parts:
        if re.match(r'^(19|20)\d{2}$', part):
            return f"{part}-01-01"
    return ""


def create_webapp(config=None):
    if config is None:
        config = load_config()

    db = Database(config.output.db_path)
    hide_persons = set(config.hide_persons or [])
    thumbs_dir = Path(config.output.thumbnails_dir).resolve()

    app = Flask(__name__)
    app.logger.setLevel(logging.WARNING)

    @app.route("/")
    def index():
        return render_template_string(APP_HTML)

    @app.route("/api/stats")
    def api_stats():
        stats = db.get_scan_stats()
        persons = db.conn.execute(
            "SELECT person_name, COUNT(*) as count FROM matches GROUP BY person_name"
        ).fetchall()
        person_list = [
            {"name": r[0], "count": r[1]}
            for r in persons if r[0] not in hide_persons
        ]
        described = db.conn.execute(
            "SELECT COUNT(*) FROM matches WHERE description IS NOT NULL"
        ).fetchone()[0]
        return jsonify({
            "stats": stats,
            "persons": person_list,
            "descriptions_done": described,
        })

    @app.route("/api/matches")
    def api_matches():
        person = request.args.get("person", "")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
        offset = (page - 1) * per_page

        query = """SELECT person_name, file_path, file_type, confidence,
                          timestamp_start, timestamp_end, thumbnail_path, description
                   FROM matches WHERE 1=1"""
        params = []

        if person:
            query += " AND person_name = ?"
            params.append(person)
        for hp in hide_persons:
            query += " AND person_name != ?"
            params.append(hp)

        query += " ORDER BY confidence DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        rows = db.conn.execute(query, params).fetchall()

        count_query = "SELECT COUNT(*) FROM matches WHERE 1=1"
        count_params = []
        if person:
            count_query += " AND person_name = ?"
            count_params.append(person)
        for hp in hide_persons:
            count_query += " AND person_name != ?"
            count_params.append(hp)
        total = db.conn.execute(count_query, count_params).fetchone()[0]

        matches = []
        for r in rows:
            fp = r[1]
            matches.append({
                "person_name": r[0], "file_path": fp, "file_name": Path(fp).name,
                "file_type": r[2], "confidence": r[3],
                "timestamp_start": r[4], "timestamp_end": r[5],
                "thumbnail": Path(r[6]).name if r[6] else None,
                "description": r[7], "date": extract_date_from_path(fp),
            })

        return jsonify({
            "matches": matches, "total": total, "page": page,
            "per_page": per_page, "pages": (total + per_page - 1) // per_page,
        })

    @app.route("/api/matches/by-date")
    def api_matches_by_date():
        person = request.args.get("person", "")
        query = """SELECT person_name, file_path, file_type, confidence,
                          timestamp_start, timestamp_end, thumbnail_path, description
                   FROM matches WHERE 1=1"""
        params = []
        if person:
            query += " AND person_name = ?"
            params.append(person)
        for hp in hide_persons:
            query += " AND person_name != ?"
            params.append(hp)
        query += " ORDER BY file_path"
        rows = db.conn.execute(query, params).fetchall()

        by_date = {}
        for r in rows:
            fp = r[1]
            date_str = extract_date_from_path(fp) or "Unknown Date"
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append({
                "person_name": r[0], "file_path": fp, "file_name": Path(fp).name,
                "file_type": r[2], "confidence": r[3],
                "timestamp_start": r[4], "timestamp_end": r[5],
                "thumbnail": Path(r[6]).name if r[6] else None,
                "description": r[7],
            })

        sorted_dates = sorted(by_date.keys(), reverse=True)
        result = [{"date": d, "matches": by_date[d], "count": len(by_date[d])}
                  for d in sorted_dates]
        return jsonify({"groups": result, "total_dates": len(result)})

    @app.route("/thumb/<path:filename>")
    def serve_thumb(filename):
        return send_from_directory(str(thumbs_dir), filename)

    @app.route("/file")
    def serve_file():
        path = request.args.get("path", "")
        if path and os.path.exists(path):
            return send_file(path)
        return "Not found", 404

    return app


APP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Face Detection Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f0f0f;color:#e0e0e0}
.header{padding:1.5rem 2rem;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:1.5rem;color:#fff}
.stats-bar{display:flex;gap:2rem;font-size:.85rem;color:#888}
.stats-bar span.val{color:#4fc3f7;font-weight:600}
.controls{padding:1rem 2rem;display:flex;gap:1rem;align-items:center;border-bottom:1px solid #1a1a1a}
.controls select,.controls button{background:#1a1a1a;color:#e0e0e0;border:1px solid #333;padding:.4rem .8rem;border-radius:6px;cursor:pointer;font-size:.85rem}
.controls button:hover{border-color:#4fc3f7}
.controls button.active{background:#4fc3f7;color:#000;border-color:#4fc3f7}
.date-group{padding:0 2rem}
.date-title{padding:1rem 0 .5rem;color:#4fc3f7;font-size:1.1rem;font-weight:600;border-bottom:1px solid #222;margin-bottom:.75rem;position:sticky;top:0;background:#0f0f0f;z-index:10}
.date-title .count{color:#666;font-size:.8rem;font-weight:400;margin-left:.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:.75rem;padding-bottom:1rem}
.card{background:#1a1a1a;border-radius:8px;overflow:hidden;border:1px solid #2a2a2a;cursor:pointer;transition:border-color .2s}
.card:hover{border-color:#4fc3f7}
.card img{width:100%;height:160px;object-fit:cover;background:#111}
.card .no-thumb{width:100%;height:160px;background:#111;display:flex;align-items:center;justify-content:center;color:#444;font-size:.75rem}
.card .info{padding:.6rem;font-size:.8rem}
.card .info .name{color:#ccc;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .info .meta{color:#666;font-size:.7rem;margin-top:.2rem}
.card .info .desc{color:#888;font-size:.7rem;margin-top:.3rem;line-height:1.3;max-height:40px;overflow:hidden}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.65rem;font-weight:600}
.badge-person{background:#1a237e;color:#9fa8da}
.conf-high{color:#a5d6a7}.conf-mid{color:#ffcc80}.conf-low{color:#ef9a9a}
.lightbox{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.95);z-index:1000;justify-content:center;align-items:center;flex-direction:column}
.lightbox.active{display:flex}
.lightbox img{max-width:92vw;max-height:75vh;object-fit:contain;border-radius:8px}
.lightbox .lb-info{color:#ccc;margin-top:1rem;text-align:center;max-width:80vw}
.lightbox .lb-info .lb-name{font-size:.9rem}
.lightbox .lb-info .lb-path{color:#666;font-size:.75rem;margin-top:.2rem;word-break:break-all}
.lightbox .lb-info .lb-desc{color:#999;font-size:.8rem;margin-top:.5rem;max-height:80px;overflow-y:auto;line-height:1.4}
.lightbox .lb-close{position:absolute;top:1.5rem;right:2rem;color:#888;font-size:2rem;cursor:pointer}
.lightbox .lb-close:hover{color:#fff}
.lb-nav{position:absolute;top:50%;transform:translateY(-50%);color:#555;font-size:3rem;cursor:pointer;user-select:none;padding:0 1.5rem}
.lb-nav:hover{color:#fff}
.lb-prev{left:0}.lb-next{right:0}
.loading{text-align:center;padding:3rem;color:#666}
</style>
</head>
<body>
<div class="header">
    <h1>Face Detection Dashboard</h1>
    <div class="stats-bar" id="stats"></div>
</div>
<div class="controls">
    <select id="personFilter"></select>
    <button id="btnByDate" class="active">By Date</button>
    <button id="btnByConf">By Confidence</button>
    <span id="totalCount" style="color:#666;font-size:.85rem;margin-left:auto"></span>
</div>
<div id="content"></div>
<div class="lightbox" id="lightbox">
    <span class="lb-close">&times;</span>
    <span class="lb-nav lb-prev">&#8249;</span>
    <span class="lb-nav lb-next">&#8250;</span>
    <img id="lb-img" src="">
    <div class="lb-info">
        <div class="lb-name" id="lb-name"></div>
        <div class="lb-path" id="lb-path"></div>
        <div class="lb-desc" id="lb-desc"></div>
    </div>
</div>
<script>
let view='date',currentPerson='',allCards=[],lbIdx=-1;
const $=id=>document.getElementById(id);

async function loadStats(){
    const d=await(await fetch('/api/stats')).json();
    const s=d.stats;
    const el=$('stats');
    while(el.firstChild)el.removeChild(el.firstChild);
    const items=['Scanned: '+(s.processed_files||0),'Matches: '+(s.matched_files||0),'Described: '+d.descriptions_done];
    d.persons.forEach(p=>items.push(p.name+': '+p.count));
    items.forEach((t,i)=>{
        if(i>0){const sp=document.createElement('span');sp.textContent=' | ';el.appendChild(sp)}
        const sp=document.createElement('span');sp.className='val';sp.textContent=t;el.appendChild(sp);
    });
    const sel=$('personFilter');
    while(sel.firstChild)sel.removeChild(sel.firstChild);
    const opt0=document.createElement('option');opt0.value='';opt0.textContent='All Persons';sel.appendChild(opt0);
    d.persons.forEach(p=>{const o=document.createElement('option');o.value=p.name;o.textContent=p.name+' ('+p.count+')';sel.appendChild(o)});
}

function setView(v){view=v;$('btnByDate').className=v==='date'?'active':'';$('btnByConf').className=v==='confidence'?'active':'';loadContent()}
$('btnByDate').onclick=()=>setView('date');
$('btnByConf').onclick=()=>setView('confidence');
$('personFilter').onchange=e=>{currentPerson=e.target.value;loadContent()};

function formatDate(iso){
    if(!iso||iso==='Unknown Date')return'Unknown Date';
    try{return new Date(iso+'T00:00:00').toLocaleDateString(undefined,{weekday:'long',year:'numeric',month:'long',day:'numeric'})}
    catch(e){return iso}
}

function makeCard(m,idx){
    const card=document.createElement('div');card.className='card';card.dataset.idx=idx;
    if(m.thumbnail){const img=document.createElement('img');img.loading='lazy';img.src='/thumb/'+m.thumbnail;card.appendChild(img)}
    else{const d=document.createElement('div');d.className='no-thumb';d.textContent='No thumbnail';card.appendChild(d)}
    const info=document.createElement('div');info.className='info';
    const nm=document.createElement('div');nm.className='name';nm.textContent=m.file_name;info.appendChild(nm);
    const meta=document.createElement('div');meta.className='meta';
    const badge=document.createElement('span');badge.className='badge badge-person';badge.textContent=m.person_name;meta.appendChild(badge);
    const conf=document.createElement('span');
    conf.className=m.confidence>=.5?'conf-high':m.confidence>=.4?'conf-mid':'conf-low';
    conf.textContent=' '+(m.confidence*100).toFixed(1)+'%';meta.appendChild(conf);
    info.appendChild(meta);
    if(m.description){const desc=document.createElement('div');desc.className='desc';desc.textContent=m.description.substring(0,120)+'...';info.appendChild(desc)}
    card.appendChild(info);
    card.onclick=()=>openLB(idx);
    return card;
}

async function loadContent(){
    const el=$('content');el.textContent='Loading...';
    if(view==='date')await loadByDate(el);else await loadByConf(el);
}

async function loadByDate(el){
    const url='/api/matches/by-date'+(currentPerson?'?person='+encodeURIComponent(currentPerson):'');
    const d=await(await fetch(url)).json();
    allCards=[];el.textContent='';
    let totalM=0;
    d.groups.forEach(g=>{
        const grp=document.createElement('div');grp.className='date-group';
        const title=document.createElement('div');title.className='date-title';
        title.textContent=formatDate(g.date);
        const cnt=document.createElement('span');cnt.className='count';cnt.textContent=g.count+' photo(s)';title.appendChild(cnt);
        grp.appendChild(title);
        const grid=document.createElement('div');grid.className='grid';
        g.matches.forEach(m=>{const idx=allCards.length;allCards.push(m);grid.appendChild(makeCard(m,idx));totalM++});
        grp.appendChild(grid);el.appendChild(grp);
    });
    $('totalCount').textContent=totalM+' matches across '+d.total_dates+' dates';
}

async function loadByConf(el){
    const url='/api/matches?per_page=200'+(currentPerson?'&person='+encodeURIComponent(currentPerson):'');
    const d=await(await fetch(url)).json();
    allCards=d.matches;el.textContent='';
    $('totalCount').textContent=d.total+' total matches';
    const grp=document.createElement('div');grp.className='date-group';
    const grid=document.createElement('div');grid.className='grid';
    d.matches.forEach((m,i)=>grid.appendChild(makeCard(m,i)));
    grp.appendChild(grid);el.appendChild(grp);
}

function openLB(idx){
    lbIdx=idx;const m=allCards[idx];
    $('lb-img').src='/file?path='+encodeURIComponent(m.file_path);
    $('lb-name').textContent=m.file_name+' \u2014 '+m.person_name;
    $('lb-path').textContent=m.file_path;
    $('lb-desc').textContent=m.description||'';
    $('lightbox').classList.add('active');document.body.style.overflow='hidden';
}
function closeLB(e){
    if(e&&(e.target.classList.contains('lb-nav')||e.target.id==='lb-img'))return;
    $('lightbox').classList.remove('active');document.body.style.overflow='';lbIdx=-1;
}
function navLB(e,dir){e&&e.stopPropagation();const n=lbIdx+dir;if(n>=0&&n<allCards.length)openLB(n)}

$('lightbox').onclick=closeLB;
$('lightbox').querySelector('.lb-close').onclick=closeLB;
$('lightbox').querySelector('.lb-prev').onclick=e=>navLB(e,-1);
$('lightbox').querySelector('.lb-next').onclick=e=>navLB(e,1);
document.addEventListener('keydown',e=>{
    if(lbIdx===-1)return;
    if(e.key==='Escape')closeLB();
    else if(e.key==='ArrowLeft')navLB(null,-1);
    else if(e.key==='ArrowRight')navLB(null,1);
});

setInterval(loadStats,30000);
loadStats();loadContent();
</script>
</body>
</html>"""


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Face Detection Web Dashboard")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("-p", "--port", type=int, default=64531)
    args = parser.parse_args()

    config = load_config(args.config)
    app = create_webapp(config)
    log.info("Starting dashboard on http://localhost:%d", args.port)
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
