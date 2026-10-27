"""FMPI-inspired 141 spatial features; explicit approximation, no trained paper weights.
Paper: https://nlpr.ia.ac.cn/2006papers/gjhy/gh41.pdf
No network or playback control. Callers handle retention and labels separately.
"""
import cv2
import numpy as np
cv2.setNumThreads(1)
KERNELS=[(cv2.getGaborKernel((11,11),2.5,a,5,.5,0,ktype=cv2.CV_32F),
          cv2.getGaborKernel((11,11),2.5,a,5,.5,np.pi/2,ktype=cv2.CV_32F))
         for a in np.arange(4)*np.pi/4]

def extract(rgb):
    rgb=np.asarray(rgb,dtype=np.uint8).copy()
    if rgb.shape != (270,480,3): raise ValueError('requires 480x270 RGB')
    # Prevent learning the already deployed Sponsored indicator as a new benefit.
    rgb[17:44,12:92]=np.median(rgb[44:55,12:92],axis=(0,1)).astype(np.uint8)
    image=cv2.resize(rgb,(160,96),interpolation=cv2.INTER_AREA)
    luv=cv2.cvtColor(image,cv2.COLOR_RGB2Luv)//16
    gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
    edges=cv2.Canny(gray,50,150)>0
    g=gray.astype(np.float32)/255
    responses=[np.hypot(cv2.filter2D(g,-1,k),cv2.filter2D(g,-1,q)) for k,q in KERNELS]
    features=[]
    def hist(a): return np.bincount(a.ravel(),minlength=16)/a.size
    for y in range(0,96,24):
        for x in range(0,160,40):
            sl=np.s_[y:y+24,x:x+40]
            features.extend(float(hist(luv[sl][:,:,c]).max()) for c in range(3))
            features.append(float(edges[sl].mean()))
            features.extend(float(r[sl].mean()) for r in responses)
    for c in range(3): features.extend(np.sort(hist(luv[:,:,c]))[-3:][::-1])
    dx=cv2.Sobel(g,cv2.CV_32F,1,0);dy=cv2.Sobel(g,cv2.CV_32F,0,1)
    angle=(np.arctan2(dy,dx)+np.pi)%np.pi
    orient=np.minimum((angle*4/np.pi).astype(int),3)
    features.extend(np.bincount(orient[edges],minlength=4)/max(1,int(edges.sum())))
    variance=np.maximum(0,cv2.blur(g*g,(5,5))-cv2.blur(g,(5,5))**2)
    flat=float(np.mean(variance<.0005))
    out=np.asarray(features,dtype=np.float32)
    assert out.shape==(141,) and np.isfinite(out).all()
    return out,flat
