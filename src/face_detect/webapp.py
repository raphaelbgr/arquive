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
            thumb = Path(r[6]).name if r[6] else None
            # Check for video frame thumbnail
            vthumb = None
            if r[2] == "video" and r[4] is not None:
                vt_name = f"{Path(fp).stem}_{r[4]:.1f}s.jpg"
                if (video_thumbs_dir / vt_name).exists():
                    vthumb = vt_name
            matches.append({
                "person_name": r[0], "file_path": fp, "file_name": Path(fp).name,
                "file_type": r[2], "confidence": r[3],
                "timestamp_start": r[4], "timestamp_end": r[5],
                "thumbnail": thumb, "video_thumb": vthumb,
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
            thumb = Path(r[6]).name if r[6] else None
            vthumb = None
            if r[2] == "video" and r[4] is not None:
                vt_name = f"{Path(fp).stem}_{r[4]:.1f}s.jpg"
                if (video_thumbs_dir / vt_name).exists():
                    vthumb = vt_name
            by_date[date_str].append({
                "person_name": r[0], "file_path": fp, "file_name": Path(fp).name,
                "file_type": r[2], "confidence": r[3],
                "timestamp_start": r[4], "timestamp_end": r[5],
                "thumbnail": thumb, "video_thumb": vthumb,
                "description": r[7],
            })

        sorted_dates = sorted(by_date.keys(), reverse=True)
        result = [{"date": d, "matches": by_date[d], "count": len(by_date[d])}
                  for d in sorted_dates]
        return jsonify({"groups": result, "total_dates": len(result)})

    video_thumbs_dir = (Path(config.output.thumbnails_dir) / ".." / "video_thumbs").resolve()

    @app.route("/thumb/<path:filename>")
    def serve_thumb(filename):
        return send_from_directory(str(thumbs_dir), filename)

    @app.route("/vthumb/<path:filename>")
    def serve_video_thumb(filename):
        return send_from_directory(str(video_thumbs_dir), filename)

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
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f0f0f;color:#e0e0e0;display:flex;height:100vh;overflow:hidden}
.sidebar{width:220px;min-width:220px;background:#111;border-right:1px solid #222;display:flex;flex-direction:column;height:100vh}
.sidebar .logo{padding:1.2rem 1rem;font-size:1.1rem;font-weight:700;color:#fff;border-bottom:1px solid #222}
.sidebar nav{flex:1;padding:.5rem 0}
.sidebar nav a{display:flex;align-items:center;gap:.6rem;padding:.7rem 1rem;color:#888;text-decoration:none;font-size:.85rem;border-left:3px solid transparent;transition:all .15s}
.sidebar nav a:hover{color:#ccc;background:#1a1a1a}
.sidebar nav a.active{color:#4fc3f7;border-left-color:#4fc3f7;background:#1a1a2a}
.sidebar nav a .icon{font-size:1.1rem;width:20px;text-align:center}
.sidebar .sidebar-footer{padding:.8rem 1rem;border-top:1px solid #222;font-size:.7rem;color:#444}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.header{padding:1rem 1.5rem;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:1.3rem;color:#fff}
.stats-bar{display:flex;gap:1.5rem;font-size:.8rem;color:#888}
.stats-bar span.val{color:#4fc3f7;font-weight:600}
.controls{padding:.7rem 1.5rem;display:flex;gap:.8rem;align-items:center;border-bottom:1px solid #1a1a1a}
.controls select,.controls button{background:#1a1a1a;color:#e0e0e0;border:1px solid #333;padding:.35rem .7rem;border-radius:6px;cursor:pointer;font-size:.8rem}
.controls button:hover{border-color:#4fc3f7}
.controls button.active{background:#4fc3f7;color:#000;border-color:#4fc3f7}
.scroll-area{flex:1;overflow-y:auto;overflow-x:hidden}
.date-group{padding:0 1.5rem}
.date-title{padding:.8rem 0 .4rem;color:#4fc3f7;font-size:1rem;font-weight:600;border-bottom:1px solid #222;margin-bottom:.6rem;position:sticky;top:0;background:#0f0f0f;z-index:10}
.date-title .count{color:#666;font-size:.75rem;font-weight:400;margin-left:.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.6rem;padding-bottom:.8rem}
.card{background:#1a1a1a;border-radius:8px;overflow:hidden;border:1px solid #2a2a2a;cursor:pointer;transition:border-color .2s;position:relative}
.card:hover{border-color:#4fc3f7}
.card img,.card video{width:100%;height:150px;object-fit:cover;background:#111}
.card .no-thumb{width:100%;height:150px;background:#111;display:flex;align-items:center;justify-content:center;color:#444;font-size:.75rem}
.card .type-badge{position:absolute;top:6px;left:6px;padding:2px 6px;border-radius:3px;font-size:.6rem;font-weight:700;text-transform:uppercase}
.card .type-badge.video{background:#e65100;color:#fff}
.card .type-badge.image{background:#004d40;color:#80cbc4}
.card .play-overlay{position:absolute;top:50%;left:50%;transform:translate(-50%,-70%);width:44px;height:44px;background:rgba(0,0,0,.6);border-radius:50%;display:flex;align-items:center;justify-content:center;pointer-events:none}
.card .play-overlay:after{content:'';border-style:solid;border-width:10px 0 10px 18px;border-color:transparent transparent transparent #fff;margin-left:3px}
.card .time-badge{position:absolute;top:6px;right:6px;padding:2px 6px;border-radius:3px;font-size:.6rem;background:rgba(0,0,0,.7);color:#ccc}
.card .info{padding:.5rem;font-size:.75rem}
.card .info .name{color:#ccc;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .info .meta{color:#666;font-size:.65rem;margin-top:.15rem}
.card .info .desc{color:#888;font-size:.65rem;margin-top:.2rem;line-height:1.3;max-height:36px;overflow:hidden}
.badge{display:inline-block;padding:1px 5px;border-radius:3px;font-size:.6rem;font-weight:600}
.badge-person{background:#1a237e;color:#9fa8da}
.conf-high{color:#a5d6a7}.conf-mid{color:#ffcc80}.conf-low{color:#ef9a9a}
.lightbox{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.95);z-index:1000;justify-content:center;align-items:center;flex-direction:column}
.lightbox.active{display:flex}
.lightbox img,.lightbox video{max-width:90vw;max-height:72vh;object-fit:contain;border-radius:8px}
.lightbox .lb-info{color:#ccc;margin-top:.8rem;text-align:center;max-width:75vw}
.lightbox .lb-info .lb-name{font-size:.85rem}
.lightbox .lb-info .lb-path{color:#666;font-size:.7rem;margin-top:.2rem;word-break:break-all}
.lightbox .lb-info .lb-desc{color:#999;font-size:.75rem;margin-top:.4rem;max-height:70px;overflow-y:auto;line-height:1.4}
.lightbox .lb-close{position:absolute;top:1.2rem;right:1.5rem;color:#888;font-size:2rem;cursor:pointer}
.lightbox .lb-close:hover{color:#fff}
.lb-nav{position:absolute;top:50%;transform:translateY(-50%);color:#555;font-size:3rem;cursor:pointer;user-select:none;padding:0 1.2rem}
.lb-nav:hover{color:#fff}
.lb-prev{left:0}.lb-next{right:0}
.loading{text-align:center;padding:3rem;color:#666}
</style>
</head>
<body>
<div class="sidebar">
    <div class="logo">FaceDetect</div>
    <nav>
        <a href="#" class="active"><span class="icon">&#128100;</span> People</a>
        <a href="#" style="opacity:.4;pointer-events:none"><span class="icon">&#128202;</span> Analytics</a>
        <a href="#" style="opacity:.4;pointer-events:none"><span class="icon">&#9881;</span> Settings</a>
    </nav>
    <div class="sidebar-footer">v0.1.0 &mdash; Local AI Face Recognition</div>
</div>
<div class="main">
    <div class="header">
        <h1>People</h1>
        <div class="stats-bar" id="stats"></div>
    </div>
    <div class="controls">
        <select id="personFilter"></select>
        <button id="btnByDate" class="active">By Date</button>
        <button id="btnByConf">By Confidence</button>
        <span id="totalCount" style="color:#666;font-size:.8rem;margin-left:auto"></span>
    </div>
    <div class="scroll-area" id="content"></div>
</div>
<div class="lightbox" id="lightbox">
    <span class="lb-close">&times;</span>
    <span class="lb-nav lb-prev">&#8249;</span>
    <span class="lb-nav lb-next">&#8250;</span>
    <img id="lb-img" src="" style="display:none">
    <video id="lb-vid" controls style="display:none"></video>
    <div class="lb-info">
        <div class="lb-name" id="lb-name"></div>
        <div class="lb-path" id="lb-path"></div>
        <div class="lb-desc" id="lb-desc"></div>
    </div>
</div>
<script>
let view='date',currentPerson='',allCards=[],lbIdx=-1;
const $=id=>document.getElementById(id);

function fmtTime(s){if(s==null)return'';const m=Math.floor(s/60),sec=Math.floor(s%60);return m+':'+String(sec).padStart(2,'0')}

async function loadStats(){
    const d=await(await fetch('/api/stats')).json();
    const s=d.stats;const el=$('stats');
    while(el.firstChild)el.removeChild(el.firstChild);
    const items=['Scanned: '+(s.processed_files||0),'Matches: '+(s.matched_files||0),'Described: '+d.descriptions_done];
    d.persons.forEach(p=>items.push(p.name+': '+p.count));
    items.forEach((t,i)=>{
        if(i>0){const sp=document.createElement('span');sp.textContent=' | ';el.appendChild(sp)}
        const sp=document.createElement('span');sp.className='val';sp.textContent=t;el.appendChild(sp);
    });
    const sel=$('personFilter');const prev=sel.value;
    while(sel.firstChild)sel.removeChild(sel.firstChild);
    const opt0=document.createElement('option');opt0.value='';opt0.textContent='All Persons';sel.appendChild(opt0);
    d.persons.forEach(p=>{const o=document.createElement('option');o.value=p.name;o.textContent=p.name+' ('+p.count+')';if(p.name===prev)o.selected=true;sel.appendChild(o)});
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
    const isVideo=m.file_type==='video';
    if(m.thumbnail){
        const img=document.createElement('img');img.loading='lazy';
        if(isVideo&&m.video_thumb){img.src='/vthumb/'+m.video_thumb}
        else{img.src='/thumb/'+m.thumbnail}
        card.appendChild(img);
    }else{const d=document.createElement('div');d.className='no-thumb';d.textContent=isVideo?'Video':'No thumbnail';card.appendChild(d)}
    if(isVideo){const po=document.createElement('div');po.className='play-overlay';card.appendChild(po)}
    const tb=document.createElement('span');tb.className='type-badge '+(isVideo?'video':'image');tb.textContent=isVideo?'VIDEO':'IMAGE';card.appendChild(tb);
    if(isVideo&&m.timestamp_start!=null){
        const tm=document.createElement('span');tm.className='time-badge';
        tm.textContent=fmtTime(m.timestamp_start)+(m.timestamp_end!=null?' - '+fmtTime(m.timestamp_end):'');
        card.appendChild(tm);
    }
    const info=document.createElement('div');info.className='info';
    const nm=document.createElement('div');nm.className='name';nm.textContent=m.file_name;info.appendChild(nm);
    const meta=document.createElement('div');meta.className='meta';
    const badge=document.createElement('span');badge.className='badge badge-person';badge.textContent=m.person_name;meta.appendChild(badge);
    const conf=document.createElement('span');
    conf.className=m.confidence>=.5?'conf-high':m.confidence>=.4?'conf-mid':'conf-low';
    conf.textContent=' '+(m.confidence*100).toFixed(1)+'%';meta.appendChild(conf);
    info.appendChild(meta);
    if(m.description){const desc=document.createElement('div');desc.className='desc';desc.textContent=m.description.substring(0,100)+'...';info.appendChild(desc)}
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
        const cnt=document.createElement('span');cnt.className='count';cnt.textContent=g.count+' item(s)';title.appendChild(cnt);
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
    const isVideo=m.file_type==='video';
    const imgEl=$('lb-img');const vidEl=$('lb-vid');
    if(isVideo){
        imgEl.style.display='none';vidEl.style.display='block';
        vidEl.src='/file?path='+encodeURIComponent(m.file_path);
        if(m.timestamp_start!=null)vidEl.currentTime=m.timestamp_start;
        vidEl.play().catch(()=>{});
    }else{
        vidEl.style.display='none';vidEl.pause();vidEl.src='';
        imgEl.style.display='block';imgEl.src='/file?path='+encodeURIComponent(m.file_path);
    }
    $('lb-name').textContent=m.file_name+' \u2014 '+m.person_name+(isVideo&&m.timestamp_start!=null?' ['+fmtTime(m.timestamp_start)+' - '+fmtTime(m.timestamp_end)+']':'');
    $('lb-path').textContent=m.file_path;
    $('lb-desc').textContent=m.description||'';
    $('lightbox').classList.add('active');document.body.style.overflow='hidden';
}
function closeLB(e){
    if(e&&(e.target.classList.contains('lb-nav')||e.target.id==='lb-img'||e.target.id==='lb-vid'))return;
    $('lightbox').classList.remove('active');document.body.style.overflow='';lbIdx=-1;
    $('lb-vid').pause();$('lb-vid').src='';
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
