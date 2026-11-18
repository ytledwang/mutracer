#!/usr/bin/env python3
import json,sys,os
scene_p,assets_p=sys.argv[1],sys.argv[2]
s=json.load(open(scene_p)); s=s.get('scene_json',s)
a=json.load(open(assets_p))
amap=a if isinstance(a,dict) else {}
keys=set(amap.keys()) if amap else set()
def present(url):
    if not url: return None
    for k in keys:
        if url.endswith(k) or k.endswith(url) or url in k or k in url: 
            v=amap[k]; return os.path.exists(v) if isinstance(v,str) else True
    return False
tex=s.get('textures',{}); slots=("basecolor_tex","roughness_tex","normal_tex","mask_tex","anisotropy_tex","metallic_tex","opacity_tex","emissive_tex")
used=set()
for m in s.get('meshes',{}).values():
    if isinstance(m,dict):
        for k in ('material','material_id'):
            if m.get(k): used.add(m[k])
        for v in (m.get('materials') or []): used.add(v if isinstance(v,str) else v.get('id'))
rows=[]
for mid,m in s.get('materials',{}).items():
    for sl in slots:
        t=tex.get(m.get(sl))
        if isinstance(t,dict) and t.get('urls'):
            rows.append((m.get('name'),sl,t['urls'],present(t['urls']),mid in used))
for e in s.get('environments',{}).values():
    t=tex.get(e.get('settings',{}).get('image'))
    if t: rows.append(('ENV:'+e.get('name',''),'hdri',t.get('urls'),present(t.get('urls')),True))
miss=[r for r in rows if not r[3]]
print(f"texture refs={len(rows)} unique_files={len(set(r[2] for r in rows))} missing_refs={len(miss)} missing_unique={len(set(r[2] for r in miss))}")
for u in sorted(set(r[2] for r in miss)):
    mats=sorted(set(f"{r[0]}[{r[1]}]" for r in miss if r[2]==u))
    print(' MISSING',u,'<-',', '.join(mats)[:200])
