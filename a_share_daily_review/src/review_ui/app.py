#!/usr/bin/env python3
"""
本机人工审核页（阶段2）

- 只读/写本地 output/ 草稿，不对接任何平台发帖 API
- 支持早报 / 复盘 Tab：勾选、改标题、预览、复制、导出

启动：
  cd a_share_daily_review
  python -m src.review_ui.app
  # 浏览器打开 http://127.0.0.1:8787
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from src.news.draft import DISCLAIMER_SHORT, render_markdown
from src.utils.config import get_project_root, load_config

app = FastAPI(title="A股内容审核台", description="仅本机人工审核，不自动发帖")


def output_root() -> Path:
    try:
        cfg = load_config()
        p = Path(cfg.get("paths", {}).get("output") or (get_project_root() / "output"))
    except Exception:
        p = get_project_root() / "output"
    return p


def list_dates() -> List[str]:
    root = output_root()
    if not root.exists():
        return []
    dates = []
    for d in sorted(root.iterdir(), reverse=True):
        if d.is_dir() and len(d.name) == 10 and d.name[4] == "-":
            dates.append(d.name)
    return dates[:60]


def load_morning(date: str) -> Optional[Dict[str, Any]]:
    path = output_root() / date / "morning_draft.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_review(date: str) -> Optional[Dict[str, Any]]:
    """复盘草稿 JSON；若无则尝试从 review_summary 拼一个简易结构。"""
    path = output_root() / date / "review_draft.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # 兼容：仅有 summary 文本
    alt = output_root() / date / "review_summary.txt"
    if alt.exists():
        text = alt.read_text(encoding="utf-8")
        return {
            "type": "daily_review",
            "run_date": date,
            "status": "pending_review",
            "auto_publish": False,
            "disclaimer_short": DISCLAIMER_SHORT,
            "summary_text": text,
            "llm_text": text,
            "items": [],
            "charts": [],
        }
    return None


def save_morning(date: str, payload: Dict[str, Any]) -> None:
    out = output_root() / date
    out.mkdir(parents=True, exist_ok=True)
    path = out / "morning_draft.json"
    payload["status"] = payload.get("status") or "pending_review"
    payload["auto_publish"] = False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    # 同步 md
    (out / "morning_draft_full.md").write_text(
        render_markdown(payload, mode="full"), encoding="utf-8"
    )
    (out / "morning_draft_brief.md").write_text(
        render_markdown(payload, mode="brief"), encoding="utf-8"
    )


def save_review(date: str, payload: Dict[str, Any]) -> None:
    out = output_root() / date
    out.mkdir(parents=True, exist_ok=True)
    path = out / "review_draft.json"
    payload["status"] = payload.get("status") or "pending_review"
    payload["auto_publish"] = False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    text = payload.get("llm_text") or payload.get("summary_text") or ""
    (out / "review_draft.md").write_text(text, encoding="utf-8")


class MorningSaveBody(BaseModel):
    payload: Dict[str, Any]


class ReviewSaveBody(BaseModel):
    payload: Dict[str, Any]


@app.get("/api/dates")
def api_dates():
    return {"dates": list_dates()}


@app.get("/api/morning/{date}")
def api_morning(date: str):
    data = load_morning(date)
    if not data:
        raise HTTPException(404, f"无早报草稿: {date}")
    return data


@app.post("/api/morning/{date}")
def api_morning_save(date: str, body: MorningSaveBody):
    save_morning(date, body.payload)
    return {"ok": True, "date": date}


@app.get("/api/morning/{date}/preview")
def api_morning_preview(date: str, mode: str = Query("full", pattern="^(full|brief)$")):
    data = load_morning(date)
    if not data:
        raise HTTPException(404, f"无早报草稿: {date}")
    return PlainTextResponse(render_markdown(data, mode=mode))


@app.get("/api/review/{date}")
def api_review(date: str):
    data = load_review(date)
    if not data:
        raise HTTPException(404, f"无复盘草稿: {date}")
    return data


@app.post("/api/review/{date}")
def api_review_save(date: str, body: ReviewSaveBody):
    save_review(date, body.payload)
    return {"ok": True, "date": date}


CHECKLIST = [
    "没有具体买/卖指令口吻",
    "没有收益承诺或暗示稳赚",
    "重要数字来自草稿源或行情字段",
    "海外内容未写成「A股必然如何」",
    "敏感或未核实传闻已删除",
    "已附短版免责声明",
]


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>内容审核台 · 不自动发帖</title>
<style>
  :root { --bg:#0f1419; --card:#1a2332; --line:#2d3a4d; --text:#e7ecf3; --muted:#8b9bb4; --acc:#3b82f6; --ok:#22c55e; --warn:#f59e0b; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }
  header { padding:16px 20px; border-bottom:1px solid var(--line); display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
  header h1 { font-size:18px; margin:0; font-weight:600; }
  header .badge { font-size:12px; color:var(--warn); border:1px solid var(--warn); padding:2px 8px; border-radius:999px; }
  .controls { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-left:auto; }
  select, button, textarea, input[type=text] { background:var(--card); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:14px; }
  button { cursor:pointer; }
  button.primary { background:var(--acc); border-color:var(--acc); color:#fff; }
  button.ghost { background:transparent; }
  main { display:grid; grid-template-columns: 1fr 1fr; gap:0; min-height: calc(100vh - 64px); }
  @media (max-width: 960px) { main { grid-template-columns: 1fr; } }
  .panel { padding:16px 20px; overflow:auto; max-height: calc(100vh - 64px); }
  .panel + .panel { border-left:1px solid var(--line); }
  .tabs { display:flex; gap:8px; margin-bottom:12px; }
  .tabs button.active { background:var(--acc); border-color:var(--acc); color:#fff; }
  .item { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; margin-bottom:10px; }
  .item.off { opacity:0.45; }
  .item-head { display:flex; gap:10px; align-items:flex-start; }
  .item-head input { margin-top:4px; }
  .meta { font-size:12px; color:var(--muted); margin-top:6px; }
  .meta a { color:var(--acc); }
  textarea.title { width:100%; margin-top:8px; min-height:52px; }
  #preview { white-space:pre-wrap; line-height:1.55; font-size:14px; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; min-height:200px; }
  .checklist label { display:block; font-size:13px; color:var(--muted); margin:6px 0; }
  .row { display:flex; gap:8px; flex-wrap:wrap; margin:10px 0; }
  .hint { font-size:12px; color:var(--muted); }
  #reviewEditor { width:100%; min-height:320px; line-height:1.5; }
</style>
</head>
<body>
<header>
  <h1>内容审核台</h1>
  <span class="badge">不自动发帖 · 仅本机</span>
  <div class="controls">
    <label class="hint">日期</label>
    <select id="dateSelect"></select>
    <button class="ghost" onclick="reload()">刷新</button>
    <button class="primary" onclick="save()">保存草稿</button>
    <button class="ghost" onclick="copyPreview()">复制预览</button>
  </div>
</header>
<main>
  <section class="panel">
    <div class="tabs">
      <button id="tabMorning" class="active" onclick="setTab('morning')">盘前早报</button>
      <button id="tabReview" onclick="setTab('review')">收盘复盘</button>
    </div>
    <div id="morningPane">
      <div class="row">
        <button class="ghost" onclick="setMode('full')">完整版条目</button>
        <button class="ghost" onclick="setMode('brief')">精简版条目</button>
        <span class="hint" id="morningStatus"></span>
      </div>
      <div id="morningList"></div>
    </div>
    <div id="reviewPane" style="display:none">
      <p class="hint">可直接改复盘正文；保存后写入 review_draft.md</p>
      <textarea id="reviewEditor"></textarea>
      <div id="chartList" class="hint" style="margin-top:10px"></div>
    </div>
    <div style="margin-top:16px">
      <strong>发帖前检查清单</strong>
      <div class="checklist" id="checklist"></div>
    </div>
  </section>
  <section class="panel">
    <div class="row">
      <strong>成稿预览</strong>
      <button class="ghost" onclick="refreshPreview()">更新预览</button>
      <select id="previewMode"><option value="full">完整版</option><option value="brief">精简版</option></select>
    </div>
    <div id="preview">选择日期后加载…</div>
  </section>
</main>
<script>
const CHECKS = """ + json.dumps(CHECKLIST, ensure_ascii=False) + r""";
let tab = 'morning';
let morning = null;
let review = null;
let editMode = 'full';

function el(id){ return document.getElementById(id); }

async function init(){
  const box = el('checklist');
  box.innerHTML = CHECKS.map((t,i)=>`<label><input type="checkbox" id="ck${i}"/> ${t}</label>`).join('');
  const r = await fetch('/api/dates');
  const data = await r.json();
  const sel = el('dateSelect');
  sel.innerHTML = (data.dates||[]).map(d=>`<option value="${d}">${d}</option>`).join('') || '<option value="">无草稿</option>';
  sel.onchange = reload;
  if (data.dates && data.dates[0]) reload();
}

function setTab(t){
  tab = t;
  el('tabMorning').classList.toggle('active', t==='morning');
  el('tabReview').classList.toggle('active', t==='review');
  el('morningPane').style.display = t==='morning' ? '' : 'none';
  el('reviewPane').style.display = t==='review' ? '' : 'none';
  refreshPreview();
}

function setMode(m){ editMode = m; renderMorning(); refreshPreview(); }

async function reload(){
  const date = el('dateSelect').value;
  if(!date) return;
  morning = null; review = null;
  try {
    const r = await fetch('/api/morning/'+date);
    if(r.ok) morning = await r.json();
  } catch(e){}
  try {
    const r2 = await fetch('/api/review/'+date);
    if(r2.ok) review = await r2.json();
  } catch(e){}
  el('morningStatus').textContent = morning ? ('状态: '+(morning.status||'')) : '无早报草稿';
  renderMorning();
  el('reviewEditor').value = review ? (review.llm_text || review.summary_text || '') : '';
  const charts = (review && review.charts) || [];
  el('chartList').textContent = charts.length ? ('图表: '+charts.join(', ')) : (review ? '无图表字段' : '无复盘草稿');
  refreshPreview();
}

function renderMorning(){
  const box = el('morningList');
  if(!morning){ box.innerHTML = '<p class="hint">暂无早报草稿，请先运行 python scripts/run_morning.py</p>'; return; }
  const key = editMode === 'brief' ? 'items_brief' : 'items_full';
  const items = morning[key] || [];
  box.innerHTML = items.map((it,idx)=>`
    <div class="item ${it.selected===false?'off':''}">
      <div class="item-head">
        <input type="checkbox" ${it.selected!==false?'checked':''} onchange="toggleItem(${idx}, this.checked)"/>
        <div style="flex:1">
          <div class="meta">#${it.index||idx+1} · ${it.source_name||''} · score ${it.score??''} · ${it.region||''}</div>
          <textarea class="title" onchange="editTitle(${idx}, this.value)">${escapeHtml(it.title||'')}</textarea>
          <div class="meta">${it.published||''} · <a href="${it.link||'#'}" target="_blank" rel="noopener">原文</a></div>
        </div>
      </div>
    </div>`).join('');
}

function escapeHtml(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function itemKey(){ return editMode==='brief' ? 'items_brief' : 'items_full'; }

function toggleItem(idx, checked){
  if(!morning) return;
  morning[itemKey()][idx].selected = checked;
  renderMorning(); refreshPreview();
}
function editTitle(idx, val){
  if(!morning) return;
  morning[itemKey()][idx].title = val;
  refreshPreview();
}

function buildMorningPreview(){
  if(!morning) return '无早报数据';
  const mode = el('previewMode').value;
  const key = mode==='brief' ? 'items_brief' : 'items_full';
  const rows = (morning[key]||[]).filter(x=>x.selected!==false);
  const date = morning.run_date || '';
  const mmdd = date.slice(5)||date;
  if(mode==='brief'){
    let lines = [`【盘前】${mmdd} 隔夜精选`,''];
    rows.forEach((r,i)=>lines.push(`${i+1}. ${r.title||''}`));
    lines.push(''); lines.push('⚠️ '+(morning.disclaimer_short||''));
    return lines.join('\n');
  }
  let lines = [`【盘前速览】${mmdd} · 隔夜海外`,'','🌍 隔夜必须知道'];
  rows.forEach((r,i)=>{ lines.push(`${i+1}. ${r.title||''}`); if(r.source_name) lines.push(`   · 来源：${r.source_name}`); });
  lines.push(''); lines.push('⚠️ '+(morning.disclaimer_short||''));
  return lines.join('\n');
}

function refreshPreview(){
  if(tab==='review'){
    el('preview').textContent = el('reviewEditor').value || '无复盘正文';
  } else {
    el('preview').textContent = buildMorningPreview();
  }
}

async function save(){
  const date = el('dateSelect').value;
  if(!date) return alert('无日期');
  if(tab==='morning'){
    if(!morning) return alert('无早报可保存');
    const r = await fetch('/api/morning/'+date,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({payload:morning})});
    if(!r.ok) return alert('保存失败');
    alert('早报草稿已保存（仍须人工复制发布）');
  } else {
    const text = el('reviewEditor').value;
    const payload = review || {type:'daily_review', run_date:date, status:'pending_review', auto_publish:false};
    payload.llm_text = text;
    payload.summary_text = text;
    payload.disclaimer_short = payload.disclaimer_short || """ + json.dumps(DISCLAIMER_SHORT, ensure_ascii=False) + r""";
    const r = await fetch('/api/review/'+date,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({payload})});
    if(!r.ok) return alert('保存失败');
    review = payload;
    alert('复盘草稿已保存（仍须人工复制发布）');
  }
}

async function copyPreview(){
  refreshPreview();
  const t = el('preview').textContent;
  try { await navigator.clipboard.writeText(t); alert('已复制到剪贴板'); }
  catch(e){ prompt('请手动复制：', t); }
}

el('previewMode').onchange = refreshPreview;
el('reviewEditor').addEventListener('input', ()=>{ if(tab==='review') refreshPreview(); });
init();
</script>
</body>
</html>
"""


def main():
    import uvicorn
    print("审核台: http://127.0.0.1:8787  （不自动发帖）")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")


if __name__ == "__main__":
    main()
