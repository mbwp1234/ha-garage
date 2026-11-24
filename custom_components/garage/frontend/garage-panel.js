/* Garage: Home Assistant sidebar panel.
 *
 * One vehicle page: a picture of the vehicle with a dot on each part of it that needs
 * something, the maintenance map as a road, every item ranked by urgency, live stat tiles,
 * and the log. Each item opens a sheet that IS the guide: interval, parts, fluid, torque.
 *
 * Plain web component, no build step. Data comes from the integration's websocket API
 * (garage/get, garage/add, garage/update, garage/delete, garage/set_profile). Personal
 * things (the picture, which sensors feed the tiles, hotspot positions) come from the
 * vehicle's settings on the share, never from this file.
 */
(function () {
'use strict';
var VERSION = '0.4.3';
var TAG = 'garage-panel-' + VERSION.replace(/\./g, '-');
if (customElements.get(TAG)) return;

var CSS = [
':host{--ground:#F1F4F8;--card:#FFFFFF;--card2:#F3F5F9;--track:#E5E9F0;--edge:rgba(16,24,40,.06);--ink:#101623;--ink2:#4B5667;--ink3:#626C7C;',
'  --cav:#46617E;--over:#C2410C;--soon:#F59F00;--soonink:#9A5800;--ok:#2B8A3E;--hatch:rgba(98,108,124,.30);--scrim:rgba(10,14,22,.32);',
'  --shadow:0 1px 2px rgba(16,24,40,.04),0 12px 32px -16px rgba(16,24,40,.16);',
'  display:block;position:relative;height:calc(100dvh - var(--g-top,0px));overflow:hidden;background:var(--ground);color:var(--ink);',
'  font-family:Geist,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;font-size:13px;font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased;color-scheme:light}',
':host([dark]){--ground:#0A0E18;--card:#131925;--card2:#1A2130;--track:#242C3B;--edge:rgba(255,255,255,.06);--ink:#EDF1F7;--ink2:#AEB7C6;--ink3:#8F99AA;',
'  --cav:#8EA9C6;--over:#FF8A5B;--soon:#FFC048;--soonink:#FFC048;--ok:#51CF66;--hatch:rgba(143,153,170,.32);--scrim:rgba(0,0,0,.55);--shadow:0 0 0 1px rgba(255,255,255,.02);color-scheme:dark}',
'*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}',
'button,input,select,textarea{font:inherit;color:inherit}',
'button{border:0;background:none;padding:0;cursor:pointer}',
'[hidden]{display:none!important}',
'.scroll{position:absolute;inset:0;overflow-y:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain}',
'.app{max-width:560px;margin:0 auto;padding:0 16px calc(48px + env(safe-area-inset-bottom,0px))}',
'.cols{display:flex;flex-direction:column;gap:16px}',
'.col{display:flex;flex-direction:column;gap:16px;min-width:0}',
'@media (min-width:1060px){.app{max-width:1160px}.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:start}}',
'.top{display:flex;align-items:center;gap:6px;height:58px}',
'.iconbtn{width:44px;height:44px;border-radius:22px;display:grid;place-items:center;color:var(--ink2)}',
'.title{padding:2px 4px 18px}',
'.title h1{margin:0;font-size:34px;font-weight:650;letter-spacing:-.03em}',
'.odo{display:inline-flex;align-items:center;gap:6px;margin-top:4px;font-size:15px;font-weight:500;color:var(--ink2)}',
'.live{width:8px;height:8px;border-radius:50%;background:var(--ok)}',
'.live.off{background:var(--track)}',
'.banner{padding:12px 14px;border-radius:18px;background:color-mix(in srgb,var(--over) 14%,var(--card));color:var(--over);font-weight:600;font-size:14px}',
'.card{position:relative;background:var(--card);border:1px solid var(--edge);border-radius:28px;padding:20px;box-shadow:var(--shadow)}',
'.hd{display:flex;align-items:center;gap:10px;min-height:32px}',
'.ico{flex:none;width:32px;height:32px;border-radius:12px;display:grid;place-items:center;color:var(--cav);background:color-mix(in srgb,var(--cav) 14%,transparent)}',
'.t{font-size:15px;font-weight:600}',
'.chip{margin-left:auto;height:28px;padding:0 11px;border-radius:14px;background:var(--card2);display:inline-flex;align-items:center;gap:5px;font-size:12.5px;font-weight:600;color:var(--ink2);white-space:nowrap}',
'button.chip{cursor:pointer}',
/* hero */
'.hero{padding:0;overflow:hidden}',
'.garage{position:relative;aspect-ratio:3/2;background:#0B0F16}',
'.garage img{display:block;width:100%;height:100%;object-fit:cover}',
'.garage .noimg{position:absolute;inset:0;display:grid;place-items:center;color:#5B6676}',
'.hs{position:absolute;width:44px;height:44px;margin:-22px 0 0 -22px;display:grid;place-items:center;border-radius:50%}',
'.hs i{position:relative;width:16px;height:16px;border-radius:50%;border:2.5px solid #fff;background:var(--c)}',
'.hs.over i{--c:var(--over);box-shadow:0 0 0 4px color-mix(in srgb,var(--over) 30%,transparent);animation:pulse 2.2s ease-out infinite}',
'.hs.soon i{--c:var(--soon);box-shadow:0 0 0 4px color-mix(in srgb,var(--soon) 30%,transparent)}',
'.hs.nolog i{background:repeating-linear-gradient(45deg,#9AA4B2 0 2px,#fff 2px 4px)}',
'.hs.ok i{--c:var(--ok)}',
'.hs.sel i{transform:scale(1.35);border-color:#FFD43B}',
'.hs b{position:absolute;top:2px;right:2px;min-width:16px;height:16px;padding:0 4px;border-radius:8px;background:#101623;color:#fff;font-size:10px;font-weight:700;display:grid;place-items:center}',
'@keyframes pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--over) 55%,transparent)}100%{box-shadow:0 0 0 12px transparent}}',
'.herobody{padding:18px 20px 20px;display:flex;flex-direction:column;gap:16px}',
'.bignum{display:flex;align-items:baseline;gap:10px}',
'.bignum .n{font-size:64px;font-weight:200;letter-spacing:-.05em;line-height:.85}',
'.bignum .l{font-size:15px;font-weight:600;color:var(--ink2)}',
'.c-over{color:var(--over)}.c-soon{color:var(--soonink)}.c-ok{color:var(--ok)}.c-nolog{color:var(--ink3)}',
'.chips{display:flex;flex-wrap:wrap;gap:8px}',
'.ichip{display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 12px 0 5px;border-radius:18px;background:var(--card2);font-size:13px;font-weight:600}',
'.nb{flex:none;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:11.5px;font-weight:700}',
'.nb.over{background:var(--over);color:#fff}',
'.nb.soon{background:var(--soon);color:#2B1600}',
'.nb.ok{background:var(--card);color:var(--ink);border:2px solid var(--track)}',
'.nb.nolog{background:repeating-linear-gradient(45deg,var(--hatch) 0 2px,transparent 2px 5px);color:var(--ink2);border:1.5px dashed var(--ink3)}',
'.nb.plain{background:var(--card2);color:var(--ink2);width:22px;height:22px;font-size:11px}',
'.pri{height:56px;border-radius:28px;background:var(--cav);color:#fff;font-size:15px;font-weight:650;display:flex;align-items:center;justify-content:center;gap:8px;width:100%}',
':host([dark]) .pri{color:#0A0E18}',
'.pri.done{background:var(--ok)}',
'.pri[disabled]{opacity:.45;cursor:default}',
'.sec{height:56px;padding:0 22px;border-radius:28px;background:var(--card2);font-size:15px;font-weight:600;display:flex;align-items:center;justify-content:center}',
'.sec.danger{color:var(--over)}',
'.sec.armed{background:var(--over);color:#fff}',
/* road */
'.road{position:relative;height:150px;margin:12px 6px 0}',
'.stk{position:absolute;bottom:62px;width:24px;margin-left:-12px;display:flex;flex-direction:column-reverse;gap:4px}',
'.stk button{display:block}',
'.lane{position:absolute;left:0;right:0;bottom:50px;height:6px;border-radius:3px;background:repeating-linear-gradient(90deg,var(--track) 0 10px,transparent 10px 16px)}',
'.lane i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--ink)}',
'.tick{position:absolute;bottom:22px;transform:translateX(-50%);font-size:11px;font-weight:600;color:var(--ink3)}',
'.now{position:absolute;bottom:41px;width:34px;margin-left:-17px;color:var(--cav)}',
'.nologrow{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:4px;padding-top:14px;border-top:1px solid var(--track)}',
'.q{width:24px;height:24px;display:grid;place-items:center;color:var(--ink3)}',
/* list */
'.grp{display:flex;align-items:center;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ink3);padding:14px 4px 4px}',
'.grp button{margin-left:auto;height:30px;padding:0 10px;border-radius:15px;background:var(--card2);font-size:12px;letter-spacing:0;text-transform:none;color:var(--ink2)}',
'.row{display:grid;grid-template-columns:24px 92px minmax(0,1fr) 84px;align-items:center;gap:12px;height:52px;padding:0 4px;width:100%;text-align:left}',
'.row .nm{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
'.bar{position:relative;height:8px;border-radius:4px;background:var(--track);overflow:hidden}',
'.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:4px}',
'.bar i.over{background:var(--over)}.bar i.soon{background:var(--soon)}.bar i.ok{background:var(--cav)}',
'.bar i.nolog{background:repeating-linear-gradient(45deg,var(--hatch) 0 3px,transparent 3px 7px)}',
'.val{text-align:right;font-size:16px;font-weight:500;letter-spacing:-.01em}',
'.val small{display:block;font-size:11px;font-weight:600;color:var(--ink3);letter-spacing:0}',
'.val.over{color:var(--over)}.val.soon{color:var(--soonink)}.val.nolog{color:var(--ink3)}',
/* tiles */
'.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}',
'.tile{display:flex;flex-direction:column;gap:12px;padding:16px;border-radius:24px;min-height:150px}',
'.tile .num{font-size:30px;font-weight:300;letter-spacing:-.035em;line-height:1}',
'.tile .num small{font-size:.5em;font-weight:500;color:var(--ink2);margin-left:2px;letter-spacing:0}',
'.tl{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--ink2)}',
'.tl svg{color:var(--cav)}',
'.tl .age{margin-left:auto;font-size:11px;color:var(--ink3);font-weight:600}',
'.gfx{margin-top:auto}',
'.meter{position:relative;height:10px;border-radius:5px;background:var(--track)}',
'.meter .band{position:absolute;top:0;bottom:0;border-radius:5px}',
'.meter .mk{position:absolute;top:50%;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;background:var(--card);border:3px solid var(--ink)}',
'.tank{position:relative;height:30px;border-radius:10px;background:var(--track);overflow:hidden}',
'.tank i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,color-mix(in srgb,var(--cav) 70%,transparent),var(--cav))}',
'.tank b{position:absolute;top:6px;bottom:6px;width:1.5px;background:color-mix(in srgb,var(--card) 70%,transparent)}',
'.hatchbox{height:30px;border-radius:10px;background:repeating-linear-gradient(45deg,var(--hatch) 0 3px,transparent 3px 8px)}',
'.mini{font-size:11px;font-weight:600;color:var(--ink3)}',
/* log */
'.entry{display:grid;grid-template-columns:96px 70px minmax(0,1fr);align-items:center;gap:10px;min-height:50px;padding:6px 4px;width:100%;text-align:left;border-top:1px solid var(--track)}',
'.entry:first-of-type{border-top:0}',
'.entry .d{font-size:13px;font-weight:600}',
'.entry .o{font-size:13px;color:var(--ink2);text-align:right}',
'.entry .its{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end}',
'.edited{font-size:10px;font-weight:700;color:var(--ink3);margin-left:4px}',
'.more{width:100%;height:44px;margin-top:6px;border-radius:22px;background:var(--card2);font-weight:600;color:var(--ink2)}',
/* sheets */
'.scrim{position:absolute;inset:0;background:var(--scrim);opacity:0;transition:opacity .2s}',
'.scrim.on{opacity:1}',
'.sheet{position:absolute;left:0;right:0;bottom:0;max-height:92%;display:flex;flex-direction:column;background:var(--card);border-radius:30px 30px 0 0;box-shadow:0 -20px 60px -20px rgba(0,0,0,.4);transform:translateY(100%);transition:transform .28s cubic-bezier(.2,.8,.2,1)}',
'.sheet.on{transform:none}',
'@media (min-width:700px){.sheet{left:50%;width:560px;margin-left:-280px}}',
'.sheet .in{overflow-y:auto;padding:10px 20px calc(24px + env(safe-area-inset-bottom,0px));display:flex;flex-direction:column;gap:16px}',
'.grab{width:40px;height:5px;border-radius:3px;background:var(--track);margin:0 auto}',
'.shd{display:flex;align-items:center;gap:10px}',
'.shd .t{font-size:20px;font-weight:650;letter-spacing:-.02em}',
'.shd .x{margin-left:auto;width:44px;height:44px;border-radius:22px;display:grid;place-items:center;background:var(--card2);color:var(--ink2);flex:none}',
'.shd .nb{width:30px;height:30px;font-size:13px}',
'.facts{display:flex;flex-wrap:wrap;gap:8px}',
'.spec{min-height:32px;padding:6px 12px;border-radius:16px;background:var(--card2);display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;color:var(--ink2)}',
'.spec b{color:var(--ink);font-weight:650}',
'.notes{margin:0;padding:0 4px;list-style:none;display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--ink2)}',
'.seg{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;padding:4px;border-radius:24px;background:var(--card2)}',
'.seg button{height:42px;border-radius:20px;font-weight:600;font-size:13px;color:var(--ink2)}',
'.seg button[aria-pressed="true"]{background:var(--card);color:var(--ink);box-shadow:var(--shadow)}',
'.chart{position:relative;height:150px}',
'.bars{position:absolute;left:0;right:0;top:0;bottom:20px;display:flex;align-items:flex-end;gap:5px}',
'.bars i{flex:1;max-width:28px;border-radius:6px 6px 3px 3px;background:color-mix(in srgb,var(--cav) 55%,transparent);min-height:3px}',
'.bars i.cur.over{background:var(--over)}.bars i.cur.soon{background:var(--soon)}.bars i.cur.ok{background:var(--cav)}',
'.line{position:absolute;left:0;right:0;border-top:2px dashed var(--ink3);opacity:.7}',
'.line b{position:absolute;right:0;top:-19px;font-size:11px;font-weight:700;color:var(--ink3)}',
'.chartx{position:absolute;left:0;right:0;bottom:0;display:flex;justify-content:space-between;font-size:10.5px;font-weight:600;color:var(--ink3)}',
'.btns{display:grid;grid-template-columns:1fr auto;gap:10px}',
'.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}',
'.fld{display:flex;flex-direction:column;gap:4px;padding:10px 14px;border-radius:18px;background:var(--card2)}',
'.fld.wide{grid-column:1/-1}',
'.fld label{font-size:11.5px;font-weight:600;color:var(--ink3)}',
'.fld input,.fld textarea{font-size:16px;font-weight:600;background:none;border:0;padding:0;outline:none;width:100%;min-width:0;resize:none}',
'.pick{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}',
'.it{position:relative;min-height:74px;padding:6px 2px;border-radius:18px;background:var(--card2);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink2);border:2px solid transparent;text-align:center}',
'.it .nb{width:26px;height:26px;background:var(--card);color:var(--ink);border:2px solid var(--track)}',
'.it.due .nb{border-color:var(--over)}',
'.it[aria-pressed="true"]{border-color:var(--cav);background:color-mix(in srgb,var(--cav) 14%,var(--card2));color:var(--ink)}',
'.it[aria-pressed="true"] .nb{background:var(--cav);border-color:var(--cav);color:#fff}',
':host([dark]) .it[aria-pressed="true"] .nb{color:#0A0E18}',
'.err{color:var(--over);font-weight:600;font-size:13px;padding:0 4px}',
'.acts{display:flex;flex-direction:column;gap:8px}',
'.act{display:grid;grid-template-columns:minmax(0,1fr) 210px;align-items:center;gap:10px;font-size:13px;font-weight:600;padding-left:4px}',
'.act .seg button{height:36px}',
/* full map */
'.poster{display:flex;align-items:flex-end;gap:6px;overflow-x:auto;overflow-y:hidden;overscroll-behavior-x:contain;padding:8px 2px 4px;scroll-snap-type:x proximity}',
'.pc{flex:none;width:34px;display:flex;flex-direction:column;align-items:center;gap:4px;scroll-snap-align:center}',
'.pc .stack{display:flex;flex-direction:column-reverse;gap:3px}',
'.pc .sev{font-size:10px;font-weight:700;color:var(--over);min-height:14px;text-align:center;line-height:1.2}',
'.pc .mk{font-size:10.5px;font-weight:700;color:var(--ink3);padding-top:4px;border-top:2px solid var(--track);width:100%;text-align:center}',
'.pc.past{opacity:.45}',
'.pc.here .mk{color:var(--cav);border-top-color:var(--cav)}',
'.pn{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:10.5px;font-weight:700;border:2px solid var(--ink3);color:var(--ink)}',
'.pn.insp{border-color:var(--soon);color:var(--soonink)}',
'.pn.done{background:var(--ok);border-color:var(--ok);color:#fff}',
'.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;font-weight:600;color:var(--ink2);align-items:center}',
'.legend span{display:inline-flex;align-items:center;gap:6px}',
'.toast{position:absolute;left:50%;bottom:calc(24px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);display:flex;align-items:center;gap:12px;padding:10px 10px 10px 18px;border-radius:24px;background:var(--ink);color:var(--card);font-weight:600;box-shadow:var(--shadow);z-index:5}',
'.toast button{height:36px;padding:0 14px;border-radius:18px;background:color-mix(in srgb,var(--card) 18%,transparent);color:var(--card);font-weight:700}',
].join('\n');

var I = {
  menu: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
  odo: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 18a9 9 0 1 1 16 0"/><path d="M12 14l4-5"/></svg>',
  plus: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  check: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  x: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  map: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 18h18M7 18l3-12M17 18l-3-12M12 7v2M12 12v2"/></svg>',
  list: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/></svg>',
  log: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3h8l4 4v14H4V3z"/><path d="M8 11h8M8 15h6"/></svg>',
  q: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M9.2 9a3 3 0 1 1 4 2.8c-.8.4-1.2 1-1.2 1.8V15M12 18.5v.5"/></svg>',
  truck: '<svg width="34" height="20" viewBox="0 0 24 14" fill="currentColor" aria-hidden="true"><path d="M1 10V7.5l2-.6L5.2 3h5.6l1.4 3H23v4z"/><circle cx="6" cy="11" r="2.4" fill="var(--card)" stroke="currentColor" stroke-width="1.6"/><circle cx="18" cy="11" r="2.4" fill="var(--card)" stroke="currentColor" stroke-width="1.6"/></svg>',
  fuel: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 21V5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v16M3 21h13M4 10h11M15 8l3 2v7a1.5 1.5 0 0 0 3 0V9l-3-3"/></svg>',
  batt: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="3" y="7" width="18" height="12" rx="2"/><path d="M7 7V5M17 7V5M7 13h3M15.5 11.5v3M14 13h3"/></svg>',
  trim: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 12h16M12 4v16"/><circle cx="9" cy="12" r="2.5" fill="currentColor"/></svg>',
  flag: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 21V4M5 4h11l-2 4 2 4H5"/></svg>',
  gauge: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l3.5-5.5"/></svg>',
  engine: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 10h2V8h4V6h4v2h2l2 2h2v6h-2l-2 2H8l-2-2H4z"/></svg>',
  temp: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M14 14.8V4a2 2 0 0 0-4 0v10.8a4 4 0 1 0 4 0z"/></svg>'
};

var RANK = { over: 0, soon: 1, nolog: 2, ok: 3 };
var GROUPS = [['over', 'Overdue'], ['soon', 'Soon'], ['nolog', 'No record'], ['ok', 'Good']];

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function fmt(n) { return n == null ? '—' : Math.round(Number(n)).toLocaleString('en-US'); }
function k(n) { return n % 1000 === 0 ? (n / 1000) + 'k' : fmt(n); }
function pd(s) { var p = String(s || '').split('-'); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
function dshort(s) { var d = pd(s); return d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'; }
/* A date within ~10 months reads as "Dec 8"; further out the day is noise and the year is the point. */
function dmonth(s) {
  var d = pd(s);
  if (!d) return '';
  var far = (d.getTime() - Date.now()) / 86400000 > 300;
  return d.toLocaleDateString('en-US', far ? { month: 'short', year: 'numeric' } : { month: 'short', day: 'numeric' });
}
function today() { var d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
function ago(iso) {
  if (!iso) return '';
  var m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (!(m >= 0)) return '';
  if (m < 2) return 'now';
  if (m < 60) return Math.round(m) + 'm';
  if (m < 48 * 60) return Math.round(m / 60) + 'h';
  return Math.round(m / 1440) + 'd';
}
function num(st) {
  if (!st || st.state === 'unavailable' || st.state === 'unknown' || st.state === '') return null;
  var v = parseFloat(st.state);
  return isFinite(v) ? v : null;
}

class GaragePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._data = null;
    this._zone = null;
    this._sheet = null;
    this._img = null;
    this._imgFor = null;
    this._lastKnown = {};
    this._showAll = false;
    this._armed = null;
    this._err = '';
  }

  set hass(h) {
    var first = !this._hass;
    this._hass = h;
    var dark = !!(h.themes && h.themes.darkMode);
    if (dark !== this.hasAttribute('dark')) this.toggleAttribute('dark', dark);
    if (first) { this._mount(); this._load(); return; }
    var v = this._data && this._data.vehicle;
    if (!v) return;
    var src = h.states[v.odometer_entity];
    var sig = src ? src.state : '';
    if (sig !== this._odoSig) { this._odoSig = sig; this._soon(); }
    this._paintTiles();
  }
  get hass() { return this._hass; }
  set narrow(n) { this._narrow = n; if (this._root) this._render(); }
  set panel(p) { this._panel = p; }

  connectedCallback() {
    var self = this;
    requestAnimationFrame(function () {
      var top = self.getBoundingClientRect().top;
      self.style.setProperty('--g-top', Math.max(0, Math.round(top)) + 'px');
    });
    if (!this._poll) this._poll = setInterval(function () { if (!document.hidden) self._load(); }, 60000);
  }
  disconnectedCallback() { clearInterval(this._poll); this._poll = null; }

  _mount() {
    /* @font-face is ignored inside a shadow root, so the font is linked from the page. */
    if (!document.getElementById('garage-font')) {
      var l = document.createElement('link');
      l.id = 'garage-font'; l.rel = 'stylesheet';
      l.href = 'https://fonts.googleapis.com/css2?family=Geist:wght@200..700&display=swap';
      document.head.appendChild(l);
    }
    this.shadowRoot.innerHTML = '<style>' + CSS + '</style><div class="scroll"><div class="app" id="root"></div></div><div id="sheetwrap"></div><div id="toastwrap"></div>';
    this._root = this.shadowRoot.getElementById('root');
    this._sw = this.shadowRoot.getElementById('sheetwrap');
    this._tw = this.shadowRoot.getElementById('toastwrap');
    var self = this;
    this.shadowRoot.addEventListener('click', function (e) { self._click(e); });
  }

  _soon() {
    var self = this;
    clearTimeout(this._soonT);
    this._soonT = setTimeout(function () { self._load(); }, 2500);
  }

  async _load() {
    try {
      var entry = this._data && this._data.vehicle ? this._data.vehicle.entry_id : undefined;
      var msg = { type: 'garage/get' };
      if (entry) msg.entry_id = entry;
      var d = await this._hass.callWS(msg);
      this._data = d;
      this._err = '';
    } catch (e) {
      this._err = (e && e.message) || 'Garage did not answer.';
    }
    this._render();
    this._loadImage();
    this._loadLastKnown();
  }

  async _loadImage() {
    var v = this._data && this._data.vehicle;
    if (!v || this._imgFor === v.entry_id) return;
    this._imgFor = v.entry_id;
    try {
      var r = await this._hass.fetchWithAuth('/api/garage/' + v.entry_id + '/image');
      if (!r.ok) return;
      this._img = URL.createObjectURL(await r.blob());
      this._render();
    } catch (e) { /* no picture is fine */ }
  }

  /* A sensor that is asleep with the vehicle: show its last real reading with its age,
     never a zero and never a blank that looks like one. */
  async _loadLastKnown() {
    var ents = this._tileEntities().filter(function (id) { return num(this._hass.states[id]) === null; }, this);
    ents = ents.filter(function (id) { return !this._lastKnown[id]; }, this);
    if (!ents.length) return;
    var start = new Date(Date.now() - 10 * 86400000).toISOString();
    var end = new Date().toISOString();
    try {
      var res = await this._hass.callApi('GET', 'history/period/' + start + '?filter_entity_id=' + ents.join(',') +
        '&end_time=' + encodeURIComponent(end) + '&minimal_response&no_attributes');
      (res || []).forEach(function (series) {
        for (var i = series.length - 1; i >= 0; i--) {
          var v = parseFloat(series[i].state);
          if (isFinite(v)) {
            var id = series[0].entity_id;
            this._lastKnown[id] = { v: v, at: series[i].last_changed || series[i].last_updated };
            break;
          }
        }
      }, this);
      this._paintTiles();
    } catch (e) { /* tiles stay hatched */ }
  }

  _tileEntities() {
    var s = (this._data && this._data.settings) || {};
    var out = [];
    (s.tiles || []).forEach(function (t) {
      if (t.entity) out.push(t.entity);
      (t.entities || []).forEach(function (e) { out.push(e); });
      [t.mil, t.count, t.since].forEach(function (e) { if (e) out.push(e); });
    });
    return out;
  }

  _reading(id) {
    var st = this._hass.states[id];
    var v = num(st);
    if (v !== null) return { v: v, unit: st.attributes.unit_of_measurement, live: true, at: st.last_updated };
    var lk = this._lastKnown[id];
    if (lk) return { v: lk.v, unit: st && st.attributes.unit_of_measurement, live: false, at: lk.at };
    return null;
  }

  /* ------------------------------------------------------------------ render */
  _render() {
    if (!this._root) return;
    var d = this._data;
    var head = '<div class="top">' + (this._narrow ? '<button class="iconbtn" data-act="menu" aria-label="Menu">' + I.menu + '</button>' : '') + '</div>';
    if (!d) {
      this._root.innerHTML = head + (this._err ? '<div class="banner">' + esc(this._err) + '</div>' : '');
      return;
    }
    if (!d.vehicle) {
      this._root.innerHTML = head + '<div class="title"><h1>Garage</h1></div><div class="card">Add a vehicle under Settings → Devices &amp; services → Garage.</div>';
      return;
    }
    var v = d.vehicle;
    var src = this._hass.states[v.odometer_entity];
    var live = num(src) !== null;
    var html = head;
    html += '<div class="title"><h1>' + esc(v.name) + '</h1><div class="odo">' + I.odo + (v.odometer == null ? 'No odometer reading yet' : fmt(v.odometer) + ' mi') +
      '<span class="live' + (live ? '' : ' off') + '" title="' + (live ? 'Live' : 'Parked') + '"></span>' +
      (!live && v.odometer_as_of ? '<span class="mini">' + esc(ago(v.odometer_as_of)) + '</span>' : '') + '</div></div>';
    if (this._err) html += '<div class="banner">' + esc(this._err) + '</div>';
    if (v.error) html += '<div class="banner">' + esc(v.error) + '</div>';
    else if (v.storage && v.storage.mounted === false) html += '<div class="banner">The garage folder isn\'t mounted, so nothing can be logged right now.</div>';
    html += '<div class="cols"><div class="col">' + this._hero(v) + this._road(v) + '</div><div class="col">' +
      this._list(v) + this._tiles() + this._logCard(d.log || []) + '</div></div>';
    var y = this.shadowRoot.querySelector('.scroll').scrollTop;
    this._root.innerHTML = html;
    this.shadowRoot.querySelector('.scroll').scrollTop = y;
    this._paintTiles();
    if (this._sheet && this._sheet.kind !== 'log') this._renderSheet(true);
  }

  _items() { return (this._data.vehicle.items || []).slice(); }
  _item(n) { return this._items().find(function (s) { return s.n === n; }); }
  _sched(n) { return this._data.vehicle.schedule.items.find(function (s) { return s.n === n; }); }

  _hero(v) {
    var s = v.summary || {};
    var hs = (this._data.settings && this._data.settings.hotspots) || {};
    var zones = v.schedule.zones || {};
    var items = this._items();
    var sel = this._zone;
    var spots = '';
    var self = this;
    Object.keys(zones).forEach(function (z) {
      var pos = hs[z];
      if (!pos || !self._img) return;
      var its = items.filter(function (i) { return i.zone === z; });
      if (!its.length) return;
      var worst = its.reduce(function (a, b) { return RANK[b.status] < RANK[a] ? b.status : a; }, 'ok');
      var due = its.filter(function (i) { return i.status !== 'ok'; }).length;
      spots += '<button class="hs ' + worst + (sel === z ? ' sel' : '') + '" style="left:' + pos[0] + '%;top:' + pos[1] + '%" data-act="zone" data-z="' + esc(z) +
        '" aria-pressed="' + (sel === z) + '" aria-label="' + esc(zones[z]) + ', ' + due + ' need attention"><i></i>' + (due > 1 ? '<b>' + due + '</b>' : '') + '</button>';
    });
    var bigN, bigL, bigC, chips;
    if (sel && zones[sel]) {
      var its = items.filter(function (i) { return i.zone === sel; }).sort(function (a, b) { return RANK[a.status] - RANK[b.status]; });
      var due = its.filter(function (i) { return i.status !== 'ok'; });
      bigN = due.length; bigL = zones[sel]; bigC = due.length ? 'c-' + (due[0].status === 'nolog' ? 'nolog' : due[0].status) : 'c-ok';
      chips = its;
    } else if (s.over) {
      bigN = s.over; bigL = 'overdue'; bigC = 'c-over';
      chips = items.filter(function (i) { return i.status === 'over'; });
    } else if (s.soon) {
      bigN = s.soon; bigL = 'due soon'; bigC = 'c-soon';
      chips = items.filter(function (i) { return i.status === 'soon'; });
    } else {
      bigN = s.next ? fmt(s.next.remaining) : '—'; bigL = s.next ? 'mi to ' + s.next.short : 'all good'; bigC = 'c-ok';
      chips = [];
    }
    var chipHtml = chips.map(function (i) {
      return '<button class="ichip" data-act="item" data-n="' + i.n + '"><span class="nb ' + i.status + '">' + i.n + '</span>' + esc(i.short) + '</button>';
    }).join('');
    var pic = this._img ? '<img src="' + this._img + '" alt="' + esc(v.name) + '">' : '<div class="noimg">' + I.truck + '</div>';
    return '<section class="card hero"><div class="garage">' + pic + spots + '</div><div class="herobody">' +
      '<div class="bignum"><span class="n ' + bigC + '">' + esc(bigN) + '</span><span class="l">' + esc(bigL) + '</span></div>' +
      (chipHtml ? '<div class="chips">' + chipHtml + '</div>' : '') +
      '<button class="pri" data-act="log">' + I.plus + 'Log service</button></div></section>';
  }

  _road(v) {
    var odo = v.odometer;
    var pace = v.pace;
    var chip = pace ? '<span class="chip">≈ ' + fmt(pace) + ' mi/day</span>' : '';
    var head = '<div class="hd"><span class="ico">' + I.map + '</span><span class="t">Map</span>' + chip +
      '<button class="chip" style="margin-left:' + (chip ? '6px' : 'auto') + '" data-act="poster">Full map</button></div>';
    if (odo == null) return '<section class="card">' + head + '<div class="hatchbox" style="margin-top:14px;height:80px"></div></section>';
    var start = Math.floor((odo - 15000) / 10000) * 10000;
    if (start < 0) start = 0;
    var end = start + 55000;
    var pct = function (m) { return Math.max(0, Math.min(100, (m - start) / (end - start) * 100)); };
    var items = this._items().filter(function (i) { return i.status !== 'nolog' && i.due_at != null; });
    var buckets = [];
    items.sort(function (a, b) { return a.due_at - b.due_at; }).forEach(function (i) {
      var p = pct(i.due_at);
      if (i.due_at > end) p = 100;
      var b = buckets.find(function (x) { return Math.abs(x.p - p) < 6; });
      if (b) b.items.push(i); else buckets.push({ p: p, items: [i] });
    });
    var odoP = pct(odo);
    buckets.forEach(function (b) { if (Math.abs(b.p - odoP) < 4) b.p = Math.min(100, odoP + 6); });
    var stacks = buckets.map(function (b) {
      return '<div class="stk" style="left:' + b.p.toFixed(1) + '%">' + b.items.slice(0, 5).map(function (i) {
        return '<button data-act="item" data-n="' + i.n + '" aria-label="' + esc(i.name) + '"><span class="nb ' + i.status + '">' + i.n + '</span></button>';
      }).join('') + '</div>';
    }).join('');
    var ticks = '';
    for (var m = start; m <= end; m += 10000) ticks += '<span class="tick" style="left:' + pct(m).toFixed(1) + '%">' + (m / 1000) + 'k</span>';
    var nolog = this._items().filter(function (i) { return i.status === 'nolog'; });
    var nl = nolog.length ? '<div class="nologrow" aria-label="Never logged"><span class="q">' + I.q + '</span>' + nolog.map(function (i) {
      return '<button data-act="item" data-n="' + i.n + '" aria-label="' + esc(i.name) + '"><span class="nb nolog">' + i.n + '</span></button>';
    }).join('') + '</div>' : '';
    return '<section class="card">' + head + '<div class="road">' + stacks + '<div class="lane"><i style="width:' + odoP.toFixed(1) + '%"></i></div>' +
      '<span class="now" style="left:' + odoP.toFixed(1) + '%" role="img" aria-label="Now">' + I.truck + '</span>' + ticks + '</div>' + nl + '</section>';
  }

  _list(v) {
    var items = this._items();
    var html = '<section class="card" style="padding-top:8px;padding-bottom:10px" aria-label="Service items">';
    GROUPS.forEach(function (g) {
      var its = items.filter(function (i) { return i.status === g[0]; });
      if (!its.length) return;
      its.sort(function (a, b) { return (a.remaining == null ? 0 : a.remaining) - (b.remaining == null ? 0 : b.remaining) || a.n - b.n; });
      html += '<div class="grp">' + g[1] + (g[0] === 'nolog' ? '<button data-act="catchup">Catch up</button>' : '') + '</div>';
      its.forEach(function (i) {
        var w, val, unit;
        if (i.status === 'nolog') { w = 100; val = '—'; unit = 'no log'; }
        else {
          var used = i.interval ? (i.interval - (i.remaining || 0)) / i.interval : 0;
          w = Math.max(3, Math.min(100, used * 100));
          if (i.remaining < 0) { val = fmt(-i.remaining); unit = 'over'; }
          else { val = fmt(i.remaining); unit = i.eta ? '≈ ' + dmonth(i.eta) : 'mi'; }
        }
        html += '<button class="row" data-act="item" data-n="' + i.n + '"><span class="nb ' + i.status + '">' + i.n + '</span><span class="nm">' + esc(i.short) + '</span>' +
          '<span class="bar"><i class="' + i.status + '" style="width:' + w.toFixed(0) + '%"></i></span>' +
          '<span class="val ' + i.status + '">' + val + '<small>' + esc(unit) + '</small></span></button>';
      });
    });
    return html + '</section>';
  }

  _tiles() {
    var s = (this._data.settings && this._data.settings.tiles) || [];
    if (!s.length) return '';
    return '<div class="grid2" id="tiles">' + s.map(function (t, i) { return '<div class="card tile" data-tile="' + i + '"></div>'; }).join('') + '</div>';
  }

  _paintTiles() {
    if (!this._data || !this._data.vehicle) return;
    var s = (this._data.settings && this._data.settings.tiles) || [];
    var self = this;
    s.forEach(function (t, i) {
      var el = self.shadowRoot.querySelector('[data-tile="' + i + '"]');
      if (!el) return;
      var html = self._tile(t);
      if (el._sig !== html) { el._sig = html; el.innerHTML = html; }
    });
  }

  _tl(icon, label, r) {
    return '<div class="tl">' + icon + esc(label) + (r && !r.live ? '<span class="age">' + esc(ago(r.at)) + '</span>' : '') + '</div>';
  }

  _tile(t) {
    var v = this._data.vehicle;
    var miss = function (icon, label) { return '<div class="tl">' + icon + esc(label) + '</div><div class="num">—</div><div class="gfx"><div class="hatchbox"></div></div>'; };
    if (t.kind === 'fuel') {
      var e = v.economy || {};
      var r = v.fuel_entity ? this._reading(v.fuel_entity) : null;
      /* Live while the truck is awake; otherwise the integration's last real reading, with its age. */
      if (!r && e.litres != null) r = { v: e.litres, live: false, at: e.as_of };
      if (!r || !v.tank_l) return miss(I.fuel, 'Fuel');
      var pc = Math.max(0, Math.min(100, r.v / v.tank_l * 100));
      var gal = r.v / 3.78541;
      var mpg = e.mpg || (e.range_basis === 'assumed' ? (this._data.settings || {}).mpg : null);
      var rng = mpg ? Math.round(gal * mpg / 10) * 10 : null;
      return this._tl(I.fuel, 'Fuel', r) + '<div class="num">' + Math.round(pc) + '<small>%</small></div><div class="gfx"><div class="tank" role="img" aria-label="Tank ' + Math.round(pc) + ' percent"><i style="width:' + pc.toFixed(0) + '%"></i><b style="left:25%"></b><b style="left:50%"></b><b style="left:75%"></b></div>' +
        '<div class="mini" style="margin-top:6px">' + gal.toFixed(1) + ' gal' + (rng ? ' · ' + (e.mpg ? '' : '≈ ') + fmt(rng) + ' mi' : '') + '</div></div>';
    }
    if (t.kind === 'economy') {
      var ec = v.economy || {};
      var fills = (v.refuels || []).length;
      if (ec.mpg == null) {
        return '<div class="tl">' + I.gauge + 'Economy</div><div class="num">—</div><div class="gfx"><div class="hatchbox"></div>' +
          '<div class="mini" style="margin-top:6px">learning · ' + fills + ' fill-up' + (fills === 1 ? '' : 's') + '</div></div>';
      }
      var segs = Math.max(1, ec.segments || 1);
      var dots = ''; for (var di = 0; di < 3; di++) dots += '<i style="flex:1;height:8px;border-radius:4px;background:' + (di < segs ? 'var(--cav)' : 'var(--track)') + '"></i>';
      return '<div class="tl">' + I.gauge + 'Economy</div><div class="num">' + ec.mpg.toFixed(1) + '<small>mpg</small></div><div class="gfx"><div style="display:flex;gap:4px" role="img" aria-label="' + segs + ' tanks measured">' + dots + '</div>' +
        '<div class="mini" style="margin-top:6px">' + fills + ' fill-ups</div></div>';
    }
    if (t.kind === 'battery') {
      var rest = (v.rest || []).map(function (x) { return x.v; });
      if (rest.length) {
        var lastV = rest[rest.length - 1];
        var lo = 11.8, hi = 13.2, W = 146, H = 46;
        var y = function (x) { return (H - (Math.max(lo, Math.min(hi, x)) - lo) / (hi - lo) * H + 2).toFixed(1); };
        var step = rest.length > 1 ? W / (rest.length - 1) : 0;
        var pts = rest.map(function (x, i) { return (1 + i * step).toFixed(1) + ',' + y(x); }).join(' ');
        var bandTop = y(12.8), bandBot = y(12.4);
        return '<div class="tl">' + I.batt + 'Battery<span class="age">at rest</span></div><div class="num">' + lastV.toFixed(1) + '<small>V</small></div><div class="gfx"><svg viewBox="0 0 148 50" width="100%" height="50" role="img" aria-label="Battery at rest, last ' + rest.length + ' drives">' +
          '<rect x="0" y="' + bandTop + '" width="148" height="' + (bandBot - bandTop).toFixed(1) + '" rx="4" fill="color-mix(in srgb,var(--ok) 22%,transparent)"/>' +
          (rest.length > 1 ? '<polyline points="' + pts + '" fill="none" stroke="var(--cav)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>' : '') +
          '<circle cx="' + (1 + (rest.length - 1) * step).toFixed(1) + '" cy="' + y(lastV) + '" r="3.5" fill="var(--cav)"/></svg></div>';
      }
      var b = this._reading(t.entity);
      if (!b) return miss(I.batt, 'Battery');
      var p = Math.max(0, Math.min(100, (b.v - 11.5) / 3.5 * 100));
      return this._tl(I.batt, 'Battery', b) + '<div class="num">' + b.v.toFixed(1) + '<small>V</small></div><div class="gfx"><div class="meter" role="img" aria-label="' + b.v.toFixed(1) + ' volts">' +
        '<span class="band" style="left:0;width:20%;background:color-mix(in srgb,var(--over) 30%,transparent)"></span>' +
        '<span class="band" style="left:54%;width:40%;background:color-mix(in srgb,var(--ok) 30%,transparent)"></span>' +
        '<span class="mk" style="left:' + p.toFixed(1) + '%"></span></div></div>';
    }
    if (t.kind === 'codes') {
      var mil = this._reading(t.mil), cnt = this._reading(t.count), since = t.since ? this._reading(t.since) : null;
      if (!mil && !cnt) return miss(I.engine, 'Engine');
      var on = mil && mil.v >= 1, n = cnt ? Math.round(cnt.v) : null;
      var sinceMi = since ? (since.unit === 'km' ? since.v * 0.621371 : since.v) : null;
      var col = on ? 'var(--over)' : 'var(--ok)';
      return this._tl(I.engine, 'Engine', mil || cnt) + '<div class="num" style="color:' + col + '">' + (on ? 'On' : 'Clear') + '</div><div class="gfx">' +
        '<div style="display:flex;align-items:center;gap:8px"><span style="flex:none;width:14px;height:14px;border-radius:50%;background:' + col + ';box-shadow:0 0 0 4px color-mix(in srgb,' + col + ' 25%,transparent)"></span>' +
        '<span class="mini">' + (n == null ? '' : n + ' code' + (n === 1 ? '' : 's')) + (sinceMi != null ? (n == null ? '' : ' · ') + fmt(sinceMi) + ' mi since clear' : '') + '</span></div></div>';
    }
    if (t.kind === 'trim') {
      var rs = (t.entities || []).map(this._reading, this).filter(Boolean);
      if (!rs.length) return miss(I.trim, 'Trim');
      var avg = rs.reduce(function (a, x) { return a + x.v; }, 0) / rs.length;
      var mk = rs.map(function (x, i) {
        var q = Math.max(0, Math.min(100, (x.v + 25) / 50 * 100));
        return '<span class="mk" style="left:' + q.toFixed(1) + '%' + (i ? ';border-color:var(--cav)' : '') + '"></span>';
      }).join('');
      return this._tl(I.trim, 'Trim', rs[0]) + '<div class="num">' + (avg < 0 ? '−' : '+') + Math.abs(Math.round(avg)) + '<small>%</small></div><div class="gfx"><div class="meter" role="img" aria-label="Fuel trims ' +
        rs.map(function (x) { return x.v.toFixed(1); }).join(' and ') + ' percent">' +
        '<span class="band" style="left:30%;width:40%;background:color-mix(in srgb,var(--ok) 28%,transparent)"></span>' +
        '<span style="position:absolute;left:50%;top:-3px;bottom:-3px;width:1.5px;background:var(--ink3)"></span>' + mk + '</div></div>';
    }
    if (t.kind === 'pace') {
      var pts = (v.points || []).slice();
      if (v.odometer != null) pts.push([today(), v.odometer]);
      if (!v.pace || pts.length < 2) return miss(I.odo, 'Pace');
      var t0 = pd(pts[0][0]).getTime(), t1 = pd(pts[pts.length - 1][0]).getTime() || t0 + 1;
      var o1 = pts[pts.length - 1][1] || 1;
      var poly = pts.map(function (p) { return ((pd(p[0]).getTime() - t0) / (t1 - t0 || 1) * 146 + 1).toFixed(1) + ',' + (50 - p[1] / o1 * 46).toFixed(1); }).join(' ');
      var last = poly.split(' ').pop().split(',');
      return '<div class="tl">' + I.odo + 'Pace</div><div class="num">' + fmt(v.pace) + '<small>mi/day</small></div><div class="gfx"><svg viewBox="0 0 148 52" width="100%" height="52" role="img" aria-label="Odometer over time">' +
        '<polyline points="' + poly + '" fill="none" stroke="var(--cav)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/><circle cx="' + last[0] + '" cy="' + last[1] + '" r="3.5" fill="var(--cav)"/></svg></div>';
    }
    if (t.kind === 'since_clear') {
      var c = this._reading(t.entity);
      if (!c) return miss(I.flag, 'Since clear');
      var mi = c.unit === 'km' ? c.v * 0.621371 : c.v;
      return this._tl(I.flag, 'Since clear', c) + '<div class="num">' + fmt(mi) + '<small>mi</small></div><div class="gfx"><svg viewBox="0 0 148 20" width="100%" height="20" aria-hidden="true">' +
        '<path d="M4 10H140" stroke="var(--track)" stroke-width="6" stroke-linecap="round"/><path d="M4 10H140" stroke="var(--ok)" stroke-width="6" stroke-linecap="round" stroke-dasharray="10 6" opacity=".7"/>' +
        '<circle cx="140" cy="10" r="6" fill="var(--card)" stroke="var(--ok)" stroke-width="3"/></svg></div>';
    }
    if (t.kind === 'coolant') {
      var w = this._reading(t.entity);
      if (!w) return miss(I.temp, 'Coolant');
      var f = w.unit === '°C' ? w.v * 9 / 5 + 32 : w.v;
      var frac = Math.max(0, Math.min(1, (f - 100) / 140));
      var ang = Math.PI * (1 - frac);
      var cx = 40 + 34 * Math.cos(ang), cy = 40 - 34 * Math.sin(ang);
      return this._tl(I.temp, 'Coolant', w) + '<div class="num">' + Math.round(f) + '<small>°F</small></div><div class="gfx"><svg viewBox="0 0 80 46" width="100%" height="52" role="img" aria-label="Coolant ' + Math.round(f) + ' degrees">' +
        '<path d="M6 40 A34 34 0 0 1 74 40" fill="none" stroke="var(--track)" stroke-width="7" stroke-linecap="round"/>' +
        '<path d="M47.6 6.86 A34 34 0 0 1 70.6 25.25" fill="none" stroke="var(--ok)" stroke-width="7" stroke-linecap="round" opacity=".45"/>' +
        '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="5" fill="var(--card)" stroke="var(--ink)" stroke-width="2.6"/></svg></div>';
    }
    return '';
  }

  _logCard(log) {
    var rows = log.slice().sort(function (a, b) { return (b.date || '').localeCompare(a.date || '') || (b.odometer || 0) - (a.odometer || 0); });
    var shown = this._showAll ? rows : rows.slice(0, 6);
    var html = '<section class="card" style="padding-bottom:12px"><div class="hd"><span class="ico">' + I.log + '</span><span class="t">Log</span><span class="chip">' + rows.length + '</span></div><div style="margin-top:8px">';
    if (!rows.length) html += '<div class="hatchbox" style="height:48px"></div>';
    shown.forEach(function (e) {
      html += '<button class="entry" data-act="edit" data-id="' + esc(e.id) + '"><span class="d">' + esc(dshort(e.date)) + (e.edited ? '<span class="edited">edited</span>' : '') + '</span>' +
        '<span class="o">' + (e.odometer == null ? '—' : fmt(e.odometer)) + '</span><span class="its">' +
        (e.items || []).map(function (i) { return '<span class="nb plain">' + i.n + '</span>'; }).join('') + '</span></button>';
    });
    if (rows.length > 6) html += '<button class="more" data-act="all">' + (this._showAll ? 'Show fewer' : 'Show all ' + rows.length) + '</button>';
    return html + '</div></section>';
  }

  /* ------------------------------------------------------------------ sheets */
  _open(sheet) {
    this._sheet = sheet;
    this._armed = null;
    this._renderSheet(false);
  }

  _close() {
    var sw = this._sw;
    var sh = sw.querySelector('.sheet'), sc = sw.querySelector('.scrim');
    this._sheet = null;
    if (sh) { sh.classList.remove('on'); sc.classList.remove('on'); setTimeout(function () { if (!sw.querySelector('.sheet.on')) sw.innerHTML = ''; }, 300); }
  }

  _renderSheet(keep) {
    var s = this._sheet;
    if (!s || !this._data || !this._data.vehicle) return;
    var body = s.kind === 'item' ? this._itemSheet(s.n) : s.kind === 'poster' ? this._posterSheet() : this._logSheet(s);
    var inner = this._sw.querySelector('.sheet .in');
    if (keep && inner) { var y = inner.scrollTop; inner.innerHTML = body; inner.scrollTop = y; return; }
    this._sw.innerHTML = '<div class="scrim" data-act="close"></div><div class="sheet" role="dialog" aria-modal="true"><div class="in">' + body + '</div></div>';
    var sw = this._sw;
    requestAnimationFrame(function () {
      sw.querySelector('.scrim').classList.add('on');
      sw.querySelector('.sheet').classList.add('on');
      var here = sw.querySelector('.pc.here');
      if (here) here.scrollIntoView({ inline: 'center', block: 'nearest' });
    });
  }

  _sheetHead(title, nb) {
    return '<div class="grab" aria-hidden="true"></div><div class="shd">' + (nb || '') + '<span class="t">' + esc(title) + '</span><button class="x" data-act="close" aria-label="Close">' + I.x + '</button></div>';
  }

  _itemSheet(n) {
    var st = this._item(n), sc = this._sched(n);
    if (!st || !sc) return '';
    var v = this._data.vehicle;
    var big, unit, cls = 'c-' + st.status;
    if (st.status === 'nolog') { big = '—'; unit = 'no record yet'; }
    else if (st.remaining < 0) { big = fmt(-st.remaining); unit = 'mi over'; }
    else { big = fmt(st.remaining); unit = 'mi to go'; }
    var html = this._sheetHead(sc.name, '<span class="nb ' + st.status + '">' + n + '</span>');
    html += '<div class="bignum"><span class="n ' + cls + '">' + big + '</span><span class="l">' + unit + '</span></div>';
    var facts = ['<span class="spec">Every <b>' + k(st.interval) + '</b>' + (sc.first ? ' · first at <b>' + k(sc.first) + '</b>' : '') + '</span>'];
    if (st.last_odometer != null) facts.push('<span class="spec">Last <b>' + fmt(st.last_odometer) + '</b> · ' + esc(dshort(st.last_date)) + '</span>');
    if (st.due_at != null) facts.push('<span class="spec">Due <b>' + fmt(st.due_at) + '</b>' + (st.eta ? ' · ≈ ' + esc(dmonth(st.eta)) : '') + '</span>');
    html += '<div class="facts">' + facts.join('') + '</div>';
    if (sc.severe) {
      html += '<div class="seg" role="group" aria-label="Interval"><button data-act="profile" data-n="' + n + '" data-p="normal" aria-pressed="' + (st.profile === 'normal') + '">Normal ' + k(sc.normal) + '</button>' +
        '<button data-act="profile" data-n="' + n + '" data-p="severe" aria-pressed="' + (st.profile === 'severe') + '">Severe ' + k(sc.severe) + '</button></div>';
    }
    html += this._intervalChart(st, v);
    var spec = (sc.spec || []).map(function (x) { return '<span class="spec">' + esc(x) + '</span>'; });
    (sc.parts || []).forEach(function (p) { spec.push('<span class="spec">' + esc(p.label) + ' <b>' + esc(p.pn) + '</b></span>'); });
    (sc.torque || []).forEach(function (t) { spec.push('<span class="spec">' + esc(t.label) + ' <b>' + esc(t.ftlb) + '</b> ft·lb</span>'); });
    if (spec.length) html += '<div class="facts">' + spec.join('') + '</div>';
    if ((sc.notes || []).length) html += '<ul class="notes">' + sc.notes.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
    var done = this._sheet && this._sheet.doneId;
    html += '<div class="btns">' + (done
      ? '<button class="pri done" data-act="undo" data-id="' + esc(done) + '">' + I.check + 'Logged · Undo</button>'
      : '<button class="pri" data-act="done" data-n="' + n + '"' + (v.odometer == null ? ' disabled' : '') + '>' + I.check + (sc.kind === 'inspect' ? 'Inspected today' : 'Done today') + '</button>') +
      '<button class="sec" data-act="log" data-n="' + n + '">Log…</button></div>';
    return html;
  }

  /* Miles between consecutive services, plus the run since the last one. A dashed line
     marks the interval. With no history there are no bars at all: a hatched box, not zero. */
  _intervalChart(st, v) {
    var hist = (st.history || []).filter(function (h) { return h.odometer != null; });
    if (!hist.length) return '<div class="hatchbox" style="height:90px" role="img" aria-label="No history yet"></div>';
    var gaps = [];
    for (var i = 1; i < hist.length; i++) gaps.push({ m: hist[i].odometer - hist[i - 1].odometer, d: hist[i].date });
    var cur = v.odometer != null ? v.odometer - hist[hist.length - 1].odometer : null;
    var max = Math.max(st.interval * 1.25, cur || 0, Math.max.apply(null, gaps.map(function (g) { return g.m; }).concat([0])));
    var H = 130;
    var bars = gaps.map(function (g) { return '<i style="height:' + Math.max(3, g.m / max * H).toFixed(0) + 'px" title="' + fmt(g.m) + ' mi"></i>'; });
    if (cur != null) bars.push('<i class="cur ' + st.status + '" style="height:' + Math.max(3, cur / max * H).toFixed(0) + 'px" title="' + fmt(cur) + ' mi since last"></i>');
    var first = (hist[1] || hist[0]).date || '', lastY = String(new Date().getFullYear());
    return '<div class="chart" role="img" aria-label="Miles between services"><div class="bars">' + bars.join('') + '</div>' +
      '<div class="line" style="bottom:' + (20 + st.interval / max * H).toFixed(0) + 'px"><b>' + k(st.interval) + '</b></div>' +
      '<div class="chartx"><span>' + esc(first.slice(0, 4)) + '</span><span>now</span></div></div>';
  }

  _logSheet(s) {
    var v = this._data.vehicle;
    var sel = s.sel || [];
    var e = s.id ? (this._data.log || []).find(function (x) { return x.id === s.id; }) : null;
    var odo = e ? (e.odometer == null ? '' : e.odometer) : (s.catchup ? '' : (v.odometer == null ? '' : Math.round(v.odometer)));
    var date = e ? e.date : (s.catchup ? '' : today());
    var html = this._sheetHead(e ? 'Edit entry' : (s.catchup ? 'Catch up' : 'Log service'));
    html += '<div class="fields"><div class="fld"><label for="g-odo">Odometer</label><input id="g-odo" inputmode="numeric" autocomplete="off" value="' + esc(odo === '' ? '' : fmt(odo)) + '" placeholder="miles"></div>' +
      '<div class="fld"><label for="g-date">Date</label><input id="g-date" type="date" max="' + today() + '" value="' + esc(date) + '"></div></div>';
    var items = this._items();
    html += '<div class="pick" role="group" aria-label="What was done">' + v.schedule.items.map(function (it) {
      var st = items.find(function (x) { return x.n === it.n; }) || {};
      var due = st.status === 'over' || st.status === 'soon' || (s.catchup && st.status === 'nolog');
      return '<button class="it' + (due ? ' due' : '') + '" data-act="pick" data-n="' + it.n + '" aria-pressed="' + (sel.indexOf(it.n) >= 0) + '"><span class="nb">' + it.n + '</span>' + esc(it.short) + '</button>';
    }).join('') + '</div>';
    html += '<div class="acts" id="g-acts">' + this._actRows(s) + '</div>';
    var by = e ? (e.by || '') : (s.by || '');
    html += '<div class="seg" role="group" aria-label="Done by">' + [['self', 'Me'], ['dealer', 'Dealer'], ['shop', 'Shop']].map(function (b) {
      return '<button data-act="by" data-by="' + b[0] + '" aria-pressed="' + (by === b[0]) + '">' + b[1] + '</button>';
    }).join('') + '</div>';
    html += '<div class="fields"><div class="fld"><label for="g-cost">Cost</label><input id="g-cost" inputmode="decimal" placeholder="$" value="' + esc(e && e.cost != null ? e.cost : '') + '"></div>' +
      '<div class="fld"><label for="g-notes">Notes</label><input id="g-notes" value="' + esc(e ? e.notes || '' : '') + '"></div></div>';
    html += '<div class="err" role="alert" hidden></div>';
    var n = sel.length;
    var label = e ? 'Save' : (n ? (n === 1 ? 'Log 1 item' : 'Log ' + n + ' items') : 'Pick what was done');
    html += '<div class="btns" style="grid-template-columns:' + (e ? '1fr auto' : '1fr') + '"><button class="pri" data-act="save"' + (n ? '' : ' disabled') + '>' + I.check + label + '</button>' +
      (e ? '<button class="sec danger' + (this._armed === 'del' ? ' armed' : '') + '" data-act="del">' + (this._armed === 'del' ? 'Delete?' : 'Delete') + '</button>' : '') + '</div>';
    return html;
  }

  /* An inspection item can be inspected OR replaced: both reset its clock, but a
     replacement is a different fact (new pads), so the form asks rather than assumes. */
  _actRows(s) {
    var sched = this._data.vehicle.schedule.items;
    s.acts = s.acts || {};
    return (s.sel || []).slice().sort(function (a, b) { return a - b; }).map(function (n) {
      var it = sched.find(function (x) { return x.n === n; });
      if (!it || it.kind !== 'inspect') return '';
      var a = s.acts[n] || 'inspected';
      return '<div class="act"><span>' + esc(it.short) + '</span><div class="seg" role="group" aria-label="' + esc(it.short) + '">' +
        '<button data-act="kind" data-n="' + n + '" data-k="inspected" aria-pressed="' + (a === 'inspected') + '">Inspected</button>' +
        '<button data-act="kind" data-n="' + n + '" data-k="changed" aria-pressed="' + (a === 'changed') + '">Replaced</button></div></div>';
    }).join('');
  }

  /* The printed map, rebuilt from the schedule: every 5k to 300k, normal items as circles
     (inspect-type in amber, as the poster draws them), severe-only items in red above.
     Milestones behind the vehicle fade; a circle fills green when the log shows it done near there. */
  _posterSheet() {
    var v = this._data.vehicle, sc = v.schedule.items, odo = v.odometer || 0;
    var log = this._data.log || [];
    var near = function (n, m) {
      return log.some(function (e) {
        return e.odometer != null && Math.abs(e.odometer - m) <= 3000 && (e.items || []).some(function (i) { return i.n === n; });
      });
    };
    var cols = '';
    for (var m = 5000; m <= 300000; m += 5000) {
      var normal = [], severe = [];
      sc.forEach(function (it) {
        var every = it.normal, first = it.first || every;
        if (m === first || (m > first && (m - first) % every === 0)) normal.push(it);
        else if (it.severe && m % it.severe === 0) severe.push(it.n);
      });
      var past = m < odo - 2500, here = Math.abs(m - odo) <= 2500;
      cols += '<div class="pc' + (past ? ' past' : '') + (here ? ' here' : '') + '"><div class="sev">' + severe.join('/') + '</div><div class="stack">' +
        normal.map(function (it) {
          return '<span class="pn' + (it.kind === 'inspect' ? ' insp' : '') + (past && near(it.n, m) ? ' done' : '') + '" title="' + esc(it.name) + '">' + it.n + '</span>';
        }).join('') + '</div><div class="mk">' + (m / 1000) + 'k</div></div>';
    }
    return this._sheetHead('Maintenance map') +
      '<div class="legend"><span><span class="pn">1</span>Change</span><span><span class="pn insp">4</span>Inspect</span><span><span class="pn done">2</span>Logged</span><span style="color:var(--over)">1/5 Severe</span></div>' +
      '<div class="poster">' + cols + '</div>' +
      '<ul class="notes">' + (v.schedule.notes || []).concat([v.schedule.severe_when]).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' +
      '<div class="facts">' + sc.map(function (it) { return '<button class="spec" data-act="item" data-n="' + it.n + '"><b>' + it.n + '</b>' + esc(it.short) + '</button>'; }).join('') + '</div>';
  }

  /* ------------------------------------------------------------------ actions */
  _click(e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var a = el.dataset.act, n = el.dataset.n ? +el.dataset.n : null;
    if (a !== 'del') this._armed = null;
    if (a === 'menu') { this.dispatchEvent(new Event('hass-toggle-menu', { bubbles: true, composed: true })); return; }
    if (a === 'zone') { this._zone = this._zone === el.dataset.z ? null : el.dataset.z; this._render(); return; }
    if (a === 'item') { this._open({ kind: 'item', n: n }); return; }
    if (a === 'poster') { this._open({ kind: 'poster' }); return; }
    if (a === 'close') { this._close(); return; }
    if (a === 'all') { this._showAll = !this._showAll; this._render(); return; }
    if (a === 'log') { this._open({ kind: 'log', sel: n ? [n] : [] }); return; }
    if (a === 'catchup') {
      var nl = this._items().filter(function (i) { return i.status === 'nolog'; }).map(function (i) { return i.n; });
      this._open({ kind: 'log', sel: [], catchup: true, hint: nl });
      return;
    }
    if (a === 'edit') {
      var en = (this._data.log || []).find(function (x) { return x.id === el.dataset.id; });
      var acts = {};
      if (en) (en.items || []).forEach(function (i) { acts[i.n] = i.action; });
      if (en) this._open({ kind: 'log', id: en.id, sel: (en.items || []).map(function (i) { return i.n; }), by: en.by || '', acts: acts });
      return;
    }
    if (a === 'pick') {
      var s = this._sheet, i = s.sel.indexOf(n);
      if (i >= 0) s.sel.splice(i, 1); else s.sel.push(n);
      el.setAttribute('aria-pressed', i < 0);
      var ar = this.shadowRoot.getElementById('g-acts');
      if (ar) ar.innerHTML = this._actRows(s);
      this._paintSave();
      return;
    }
    if (a === 'kind') {
      var sk = this._sheet;
      sk.acts = sk.acts || {};
      sk.acts[n] = el.dataset.k;
      el.parentNode.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b === el); });
      return;
    }
    if (a === 'by') {
      var sh = this._sheet;
      sh.by = sh.by === el.dataset.by ? '' : el.dataset.by;
      this.shadowRoot.querySelectorAll('[data-act="by"]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.by === sh.by); });
      return;
    }
    if (a === 'save') { this._save(); return; }
    if (a === 'del') {
      if (this._armed !== 'del') {
        this._armed = 'del';
        var self = this;
        clearTimeout(this._armT);
        this._armT = setTimeout(function () { if (self._armed === 'del') { self._armed = null; self._paintDel(); } }, 5000);
        this._paintDel();
        return;
      }
      this._armed = null;
      this._write({ type: 'garage/delete', log_id: this._sheet.id }, 'Entry deleted');
      return;
    }
    if (a === 'done') { this._doneToday(n); return; }
    if (a === 'undo') { this._undo(el.dataset.id); return; }
    if (a === 'profile') { this._write({ type: 'garage/set_profile', n: n, profile: el.dataset.p }, null, true); return; }
  }

  _paintSave() {
    var b = this.shadowRoot.querySelector('[data-act="save"]');
    if (!b || !this._sheet) return;
    var n = this._sheet.sel.length, edit = !!this._sheet.id;
    b.disabled = !n;
    b.innerHTML = I.check + (edit ? 'Save' : (n ? (n === 1 ? 'Log 1 item' : 'Log ' + n + ' items') : 'Pick what was done'));
  }

  _paintDel() {
    var b = this.shadowRoot.querySelector('[data-act="del"]');
    if (!b) return;
    b.classList.toggle('armed', this._armed === 'del');
    b.textContent = this._armed === 'del' ? 'Delete?' : 'Delete';
  }

  _formEntry() {
    var q = this.shadowRoot.querySelector.bind(this.shadowRoot);
    var s = this._sheet;
    var schedule = this._data.vehicle.schedule.items;
    var KIND = { change: 'changed', inspect: 'inspected', rotate: 'rotated', grease: 'greased' };
    return {
      odometer: (q('#g-odo').value || '').replace(/[^0-9.]/g, ''),
      date: q('#g-date').value,
      cost: (q('#g-cost').value || '').replace(/[^0-9.]/g, ''),
      notes: q('#g-notes').value,
      by: s.by || '',
      items: s.sel.slice().sort(function (a, b) { return a - b; }).map(function (n) {
        var it = schedule.find(function (x) { return x.n === n; });
        var act = it.kind === 'inspect' && s.acts && s.acts[n] ? s.acts[n] : (KIND[it.kind] || 'changed');
        return { n: n, action: act };
      })
    };
  }

  async _save() {
    var s = this._sheet;
    var entry = this._formEntry();
    if (!entry.date) { this._sheetError('Pick the date it was done.'); return; }
    if (s.id) await this._write({ type: 'garage/update', log_id: s.id, entry: entry }, 'Saved');
    else await this._write({ type: 'garage/add', entry: entry }, entry.items.length === 1 ? 'Logged' : 'Logged ' + entry.items.length + ' items');
  }

  async _doneToday(n) {
    var v = this._data.vehicle;
    var it = this._sched(n);
    var KIND = { change: 'changed', inspect: 'inspected', rotate: 'rotated', grease: 'greased' };
    try {
      var r = await this._hass.callWS({ type: 'garage/add', entry_id: v.entry_id,
        entry: { odometer: Math.round(v.odometer), date: today(), items: [{ n: n, action: KIND[it.kind] }] } });
      this._sheet.doneId = r.result.id;
      await this._load();
      this._renderSheet(true);
    } catch (e) { this._toast((e && e.message) || 'Could not log that.'); }
  }

  async _undo(id) {
    try {
      await this._hass.callWS({ type: 'garage/delete', entry_id: this._data.vehicle.entry_id, log_id: id });
      this._sheet.doneId = null;
      await this._load();
      this._renderSheet(true);
    } catch (e) { this._toast((e && e.message) || 'Could not undo.'); }
  }

  async _write(msg, toast, keepSheet) {
    msg.entry_id = this._data.vehicle.entry_id;
    try {
      await this._hass.callWS(msg);
      await this._load();
      if (keepSheet) this._renderSheet(true);
      else { this._close(); if (toast) this._toast(toast); }
    } catch (e) {
      if (this._sheet && this._sheet.kind === 'log') this._sheetError((e && e.message) || 'Could not save.');
      else this._toast((e && e.message) || 'Could not save.');
    }
  }

  /* Shown in place: re-rendering the sheet would throw away what was typed. */
  _sheetError(text) {
    var el = this.shadowRoot.querySelector('.sheet .err');
    if (!el) { this._toast(text); return; }
    el.textContent = text;
    el.hidden = false;
  }

  _toast(text) {
    var tw = this._tw;
    tw.innerHTML = '<div class="toast" role="status">' + esc(text) + '</div>';
    clearTimeout(this._toastT);
    this._toastT = setTimeout(function () { tw.innerHTML = ''; }, 3500);
  }
}

customElements.define(TAG, GaragePanel);
})();
