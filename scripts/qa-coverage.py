#!/usr/bin/env python3
"""Coverage DISTRIBUTION over a glyph run, not its maximum.

The peak-pixel method this project has used since M0 takes the single most
contrasting pixel in a run. That is a MAX: once any one pixel is fully covered
it returns the 8-bit arithmetic composite exactly, and it says nothing about
the other several thousand. A reader does not read one pixel.

This solves the per-pixel coverage instead. Every pixel of an antialiased glyph
is ink over background at some alpha a:  c = ink*a + bg*(1-a).  Given the modal
background and the fully-covered ink, a is recoverable per pixel, and so is
that pixel's own contrast against the background. The output is the
distribution of those contrasts, weighted by ink mass, which is the quantity a
design decision should actually be judged on.

In-memory frame; nothing is written to disk.
"""
import json, subprocess, sys, collections, math

def grab():
    buf=subprocess.run(["grim","-t","ppm","-"],stdout=subprocess.PIPE,check=True).stdout
    assert buf[:2]==b"P6"
    idx,f=2,[]
    while len(f)<3:
        while buf[idx:idx+1].isspace(): idx+=1
        if buf[idx:idx+1]==b"#":
            while buf[idx:idx+1] not in (b"\n",b""): idx+=1
            continue
        s=idx
        while not buf[idx:idx+1].isspace(): idx+=1
        f.append(int(buf[s:idx]))
    idx+=1; w,h,_=f
    return w,h,buf[idx:idx+w*h*3]

def rgbof(s):
    s=s.lstrip("#"); return tuple(int(s[i:i+2],16) for i in (0,2,4))

def lin(v):
    v/=255.0
    return v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4
def lum(c): return 0.2126*lin(c[0])+0.7152*lin(c[1])+0.0722*lin(c[2])
def contrast(a,b):
    la,lb=lum(a),lum(b)
    if la<lb: la,lb=lb,la
    return (la+0.05)/(lb+0.05)

y0,y1,x0,x1 = (int(v) for v in sys.argv[1:5])
fills=[rgbof(v) for v in sys.argv[5:]]
w,h,px=grab()
def at(x,y):
    o=(y*w+x)*3; return (px[o],px[o+1],px[o+2])

hist=collections.Counter()
for y in range(y0,y1+1):
    for x in range(x0,x1+1): hist[at(x,y)]+=1
bg=hist.most_common(1)[0][0]
# the fully-covered ink: the peak-pixel answer, which is exactly what the old
# method returned and is used here only as the endpoint of the coverage axis.
ink,best=bg,-1
for c in hist:
    d=(c[0]-bg[0])**2+(c[1]-bg[1])**2+(c[2]-bg[2])**2
    if d>best: best,ink=d,c

def coverage(c):
    # least squares over the three channels; the ink/bg difference is the basis
    num=den=0.0
    for i in range(3):
        d=ink[i]-bg[i]
        num+=(c[i]-bg[i])*d; den+=d*d
    return max(0.0,min(1.0,num/den)) if den else 0.0

rows=[]
for c,n in hist.items():
    a=coverage(c)
    if a<=0.02: continue          # background, not part of the stroke
    rows.append((a, contrast(c,bg), n))
rows.sort(key=lambda r:r[1])
mass=sum(a*n for a,_,n in rows)
if mass<=0:
    print(json.dumps({"error":"no inked pixels"})); sys.exit(2)

def pct(p):
    # ink-mass-weighted percentile of per-pixel contrast
    want=mass*p; acc=0.0
    for a,c,n in rows:
        acc+=a*n
        if acc>=want: return c
    return rows[-1][1]

above=sum(a*n for a,c,n in rows if c>=4.5)
print(json.dumps({
 "bg":"#%02x%02x%02x"%bg, "ink":"#%02x%02x%02x"%ink,
 "peakContrast":round(contrast(ink,bg),4),
 "inkedPixels":sum(n for _,_,n in rows),
 "p10":round(pct(0.10),4), "p25":round(pct(0.25),4), "p50":round(pct(0.50),4),
 "p75":round(pct(0.75),4), "p90":round(pct(0.90),4),
 "fractionOfInkAboveAA":round(above/mass,4),
 "meanCoverage":round(sum(a*a*n for a,_,n in rows)/mass,4),
}))
