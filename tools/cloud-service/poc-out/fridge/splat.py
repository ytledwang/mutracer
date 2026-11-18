import json,struct,numpy as np,sys
from PIL import Image
snap=json.load(open('stage-fridge-scene_snapshot.json'))
assets=json.load(open('stage-fridge-assets.json'))
models=snap['models'];meshes=snap['meshes']
def glb_pos(p):
  d=open(p,'rb').read()
  cl=struct.unpack('<I',d[12:16])[0]; g=json.loads(d[20:20+cl])
  off=20+cl; bl=struct.unpack('<I',d[off:off+4])[0]; b=d[off+8:off+8+bl]
  pts=[]
  for me in g['meshes']:
    for pr in me['primitives']:
      a=g['accessors'][pr['attributes']['POSITION']]; bv=g['bufferViews'][a['bufferView']]
      o=bv.get('byteOffset',0)+a.get('byteOffset',0); st=bv.get('byteStride',12)
      arr=np.frombuffer(b,dtype=np.uint8,count=st*(a['count']-1)+12,offset=o)
      if st==12: v=np.frombuffer(b,np.float32,a['count']*3,o).reshape(-1,3)
      else: v=np.stack([np.frombuffer(b,np.float32,3,o+i*st) for i in range(a['count'])])
      pts.append(v)
  return np.concatenate(pts)
def ue_rot(r):
  roll,pitch,yaw=np.radians(r)
  SR,CR,SP,CP,SY,CY=np.sin(roll),np.cos(roll),np.sin(pitch),np.cos(pitch),np.sin(yaw),np.cos(yaw)
  X=[CP*CY,CP*SY,SP]; Y=[SR*SP*CY-CR*SY,SR*SP*SY+CR*CY,-SR*CP]; Z=[-(CR*SP*CY+SR*SY),CY*SR-CR*SP*SY,CR*CP]
  return np.array([X,Y,Z]).T
def rh_rot(r):
  a,b,c=np.radians(r)
  Rx=np.array([[1,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])
  Ry=np.array([[np.cos(b),0,np.sin(b)],[0,1,0],[-np.sin(b),0,np.cos(b)]])
  Rz=np.array([[np.cos(c),-np.sin(c),0],[np.sin(c),np.cos(c),0],[0,0,1]])
  return Rx@Ry@Rz
def M(e,rot):
  m=np.eye(4); m[:3,:3]=rot(e.get('rotation_euler') or [0,0,0])@np.diag(e.get('scale') or [1,1,1]); m[:3,3]=e.get('position') or [0,0,0]; return m
G={'xzy':np.array([[1,0,0],[0,0,1],[0,1,0]]),'x-zy':np.array([[1,0,0],[0,0,-1],[0,1,0]]),'-xzy':np.array([[-1,0,0],[0,0,1],[0,1,0]]),'id':np.eye(3)}
cache={}
def world_pts(rot,gk,sub=40):
  out=[]
  def walk(n,P):
    m=models.get(n)
    if not m or m.get('is_visible') is False: return
    W=P@M(m,rot)
    if m.get('type')=='model' and m.get('mesh'):
      u=meshes[m['mesh']]['url']
      if u not in cache: cache[u]=glb_pos(assets[u])[::sub]
      v=cache[u]@G[gk].T
      out.append(v@W[:3,:3].T+W[:3,3])
    for c in m.get('children') or []: walk(c,W)
  root=[k for k,v in models.items() if v.get('type')=='root'][0]
  walk(root,np.eye(4)); return np.concatenate(out)
def project(pts,rot,W=1024,H=576):
  cam=snap['cameras']['858db55c-ec03-4fa6-9ec4-948a6df1ea33']
  R=rot(cam['rotation_euler']); pos=np.array(cam['position'])
  if rot is ue_rot: fwd,right,up=R[:,0],R[:,1],R[:,2]
  else: fwd,right,up=R[:,0],-R[:,1],R[:,2]  # treat RH: forward X, left Y
  d=pts-pos; x=d@right; y=d@up; z=d@fwd
  hf=np.tan(np.radians(35)/2)
  u=(x/(z*hf)*0.5+0.5)*W; v=(0.5-y/(z*hf*H/W)*0.5)*H
  img=np.zeros((H,W),bool); ok=(z>0)&(u>=0)&(u<W)&(v>=0)&(v<H)
  img[v[ok].astype(int),u[ok].astype(int)]=True
  return img
ref=np.array(Image.open('ref/fridge-ref-front-329c-1024.png'))[:,:,:3].astype(float)
rm=np.abs(ref-np.median(ref.reshape(-1,3),0)).sum(2)>15
from PIL import ImageFilter
def binary_dilation(img,iterations=3):
  im=Image.fromarray((img*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2*iterations+1)); return np.array(im)>0
def score(img):
  m=binary_dilation(img,iterations=3)
  i=(m&rm).sum(); un=(m|rm).sum(); return i/un
best=None
for rn,rot in [('ue',ue_rot),('rh',rh_rot)]:
  for gk in G:
    pts=world_pts(rot,gk)
    mn,mx=pts.min(0),pts.max(0)
    img=project(pts,rot); s=score(img)
    ys,xs=np.where(img)
    print(f'{rn} {gk}: AABB size {np.round(mx-mn,3)} min {np.round(mn,3)} IoU {s:.3f} bbox x{xs.min() if len(xs) else -1}-{xs.max() if len(xs) else -1} y{ys.min() if len(ys) else -1}-{ys.max() if len(ys) else -1}')
    Image.fromarray((np.stack([img*255,rm*255,img*0],-1)).astype(np.uint8)).save(f'/tmp/splat-{rn}-{gk}.png')
print('ref bbox', np.where(rm)[1].min(),np.where(rm)[1].max(),np.where(rm)[0].min(),np.where(rm)[0].max())
