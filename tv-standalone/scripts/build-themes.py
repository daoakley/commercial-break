"""Generate local, still scene artwork for the existing EFL renderer and UI preview."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'engine' / 'themes'
OUT.mkdir(exist_ok=True)
themes = []

def rect(x,y,w,h,c):return dict(type='rectangle',x=x,y=y,width=w,height=h,color=c+'FF')
def ellipse(x,y,w,h,c):return dict(type='ellipse',x=x,y=y,width=w,height=h,color=c+'FF')
def poly(points,c):return dict(type='polygon',points=[dict(x=round(x),y=round(y)) for x,y in points],color=c+'FF')
def line(x,y,xx,yy,c):return dict(type='line',x1=round(x),y1=round(y),x2=round(xx),y2=round(yy),color=c+'FF')
def text(y,value,size,color='#F4F2EC',height=150):
    return dict(type='textblock',x=120,y=y,width=1680,height=height,text=value,size=size,font='SamsungOne',color=color+'FF',align='center',valign='center',style='plain')
def gradient(a,b):
    aa=[int(a[i:i+2],16) for i in (1,3,5)];bb=[int(b[i:i+2],16) for i in (1,3,5)]
    return [rect(0,i*24,1920,24,'#'+''.join('%02X'%round(x+(y-x)*i/44) for x,y in zip(aa,bb))) for i in range(45)]
def hill(y,amp,phase,c):
    return poly([(0,1080)]+[(x,y+math.sin(x/510+phase)*amp) for x in range(0,1921,60)]+[(1920,1080)],c)
def star(x,y,r,c):
    return poly([(x+math.sin(i*math.pi/5)*r*(1 if i%2==0 else .42),y-math.cos(i*math.pi/5)*r*(1 if i%2==0 else .42)) for i in range(10)],c)
def heart(x,y,r,c):
    return poly([(x+r*math.sin(t)**3,y-r*(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t))/16) for t in [i*math.pi/32 for i in range(64)]],c)
def base(a,b):return [rect(0,0,1920,1080,a)]+gradient(a,b)
def add(id,name,category,description,objects,accent='#C8C0AD'):
    objects += [rect(835,383,250,2,accent),text(404,'Commercial Break',102),text(560,'A MOMENT TO YOURSELF',22,accent,60)]
    scene={'infoMode':'clock','objects':objects}
    (OUT/(id+'.json')).write_text(json.dumps(scene,separators=(',',':'))+'\n')
    themes.append(dict(id=id,name=name,category=category,description=description,scene=scene))

original=json.loads((ROOT/'engine'/'scene.json').read_text())
(OUT/'default.json').write_text(json.dumps(original,indent=2)+'\n')
themes.append(dict(id='default',name='Original',category='Original',description='Your current quiet, dark break screen.',scene=original))

o=base('#171C25','#293338')
o += [hill(1000,80,1,'#33423C'),hill(1080,90,3,'#202F2C')]
for x,y in [(190,230),(1580,800),(1730,300)]:
    o += [poly([(x-8,y+250),(x+6,y-20),(x+12,y+250)],'#647166')]
    for dx,dy in [(0,0),(-45,70),(45,110)]:
        for t in range(5):
            a=t*math.tau/5;o.append(ellipse(round(x+dx+math.cos(a)*23-23),round(y+dy+math.sin(a)*23-32),46,64,'#C3A8A6'))
        o.append(ellipse(x+dx-9,y+dy-9,18,18,'#DCCCB0'))
add('spring','Spring blossom','Seasons','Soft blossoms against an evening sky.',o)

o=base('#13272D','#526964')+[ellipse(1390,145,220,220,'#D1AF78')]
o += [hill(815,26,0,'#647C78'),hill(900,25,2,'#3B5E63'),hill(1000,30,4,'#254851')]
add('summer','Summer shore','Seasons','A sunlit horizon and a quiet sea.',o)

o=base('#251C22','#584331')+[ellipse(220,180,170,170,'#B78C59'),hill(870,60,2,'#6C4B35'),hill(980,100,4,'#44382E')]
for x,y,s in [(1580,240,1),(1710,800,.65),(230,820,.7)]:
    pts=[(0,-110),(23,-48),(67,-66),(51,-15),(103,2),(40,33),(47,65),(5,47),(0,120),(-5,47),(-47,65),(-40,33),(-103,2),(-51,-15),(-67,-66),(-23,-48)]
    o.append(poly([(x+a*s,y+b*s) for a,b in pts],'#B17D4C'))
add('autumn','Autumn amber','Seasons','Copper leaves and warm layered hills.',o)

o=base('#15212F','#435263')+[ellipse(1460,150,150,150,'#D8DCD5')]
o += [poly([(0,1080),(0,925),(440,660),(840,990),(1260,700),(1920,990),(1920,1080)],'#778C96'),poly([(230,790),(440,660),(600,800),(450,755),(395,790),(348,758)],'#D1D9D8'),hill(1020,70,3,'#3E5965')]
add('winter','Winter stillness','Seasons','Snow-covered peaks under a pale moon.',o)

o=base('#14211F','#30433B')
for x,y,s,c in [(180,830,1.2,'#405A4B'),(1610,810,1.4,'#526653'),(1800,930,1,'#324C40'),(330,990,.65,'#57715B')]:
    for k in range(3):
        yy=y+k*80*s;w=(75+k*30)*s;o.append(poly([(x,yy-160*s),(x-w,yy),(x+w,yy)],c))
for x,y in [(300,210),(1550,200),(1720,490),(140,500)]:o.append(star(x,y,10,'#C3AF7A'))
add('christmas','Christmas woodland','US holidays','Evergreen silhouettes and quiet golden stars.',o)

o=base('#251923','#4B303B')
o += [heart(320,270,95,'#8F5B64'),heart(1600,835,140,'#9E6D70'),hill(1080,80,2,'#69434C')]
add('valentines','Valentine’s Day','US holidays','A restrained composition in rose and plum.',o,'#D4B6AB')

o=base('#172036','#273754')
for x,y in [(230,240),(1580,220),(1720,830),(340,850)]:
    for a in range(12):
        t=a*math.tau/12;o.append(line(x+math.sin(t)*55,y+math.cos(t)*55,x+math.sin(t)*105,y+math.cos(t)*105,'#BDA76F'))
    o.append(star(x,y,12,'#DED0A6'))
add('new-year','New Year','US holidays','Still golden starbursts in a midnight sky.',o,'#CCBC94')

o=base('#162333','#354356')
o += [hill(955,70,1,'#79464A'),hill(1080,75,3,'#B9B5A7')]
for x,y,r in [(240,220,26),(1660,260,18),(1530,150,11)]:o.append(star(x,y,r,'#D9D8C9'))
add('independence','Independence Day','US holidays','Muted red, white and blue with an open starry sky.',o)

o=base('#1D1C2C','#4B3C3C')+[ellipse(1430,140,225,225,'#C6A576'),ellipse(1500,100,220,220,'#282532')]
o += [hill(960,80,2,'#443F46'),hill(1055,100,4,'#292B35')]
for x,y in [(240,820),(1770,860)]:
    o += [poly([(x-5,1080),(x+4,y),(x+10,1080)],'#1C2330'),line(x,y+100,x-90,y+20,'#1C2330'),line(x,y+150,x+70,y+50,'#1C2330')]
add('halloween','Halloween moon','US holidays','A crescent moon above a dusky landscape.',o,'#CAB28E')

o=base('#28241D','#554B35')+[ellipse(270,180,160,160,'#BA9B64'),hill(1020,80,2,'#7D6541')]
for x in [150,210,270,1630,1690,1750]:
    o.append(poly([(x-2,1080),(x+1,755),(x+4,1080)],'#B79C68'))
    for k in range(4):
        y=790+k*30;o.append(poly([(x,y+25),(x-24,y),(x-28,y-25),(x-9,y-10)],'#B79C68'));o.append(poly([(x,y+35),(x+24,y+10),(x+28,y-15),(x+9,y)],'#B79C68'))
add('thanksgiving','Thanksgiving harvest','US holidays','Golden wheat and an earthy evening palette.',o)

o=base('#263232','#566658')+[ellipse(1450,150,180,180,'#D3C5A2'),hill(910,60,1,'#728270'),hill(1040,80,4,'#506354')]
for x,y,w,h,c in [(230,825,86,118,'#C3ACB1'),(325,855,70,96,'#D1C1A2'),(1660,880,78,110,'#9BAFC0')]:o.append(ellipse(x,y,w,h,c))
add('easter','Easter morning','US holidays','Pastel accents in a soft, green meadow.',o)

o=base('#27262B','#645448')+[ellipse(1440,160,180,180,'#C5AE87'),hill(840,115,2,'#967D60'),hill(960,105,4,'#776451'),hill(1080,90,1,'#504C43')]
add('zen-dunes','Desert quiet','Zen','Soft dunes, gentle contours and warm light.',o)
o=base('#18262C','#4E686A')+[ellipse(280,170,130,130,'#BCC8BD')]
for y,a,c in [(815,12,'#5C7474'),(875,16,'#4D696C'),(945,18,'#3E5B62'),(1020,12,'#2D4853')]:o.append(hill(y,a,y/100,c))
add('zen-water','Quiet water','Zen','A calm horizon, moonlight and broad ripples.',o)
o=base('#1B272A','#5B706D')+[ellipse(1480,170,145,145,'#C2C8B5')]
for i,c in enumerate(['#738781','#657E76','#516D65','#38564F']):
    y=760+i*100;o.append(poly([(0,1080),(0,y+40),(300,y-90),(560,y+20),(970,y-140),(1360,y+60),(1680,y-80),(1920,y+10),(1920,1080)],c))
add('zen-mountains','Mist & mountains','Zen','Layered green ridgelines fading into mist.',o)

import runpy
runpy.run_path(str(Path(__file__).with_name('skyline-art.py')))['city_scenes'](base,rect,ellipse,poly,line,add)

for mode in ('auto','day','night'):
    sequence=[city+'-'+('day' if mode=='auto' else mode) for city in ('memphis','dc','raleigh','charlotte')]
    preview=next(t['scene'] for t in themes if t['id']==sequence[0])
    themes.insert(next(i for i,t in enumerate(themes) if t['id']=='raleigh-day'),dict(id='cities-'+mode,name='Rotate cities · '+('Automatic' if mode=='auto' else mode.title()),category='City skylines',description='Memphis → DC → Raleigh → Charlotte. '+('Day and night follow Raleigh sunrise and sunset. ' if mode=='auto' else '')+'A different city for each new detected break.',automatic=mode=='auto',rotation=sequence,scene=preview))
    (OUT/('cities-'+mode+'.json')).write_text(json.dumps(preview,separators=(',',':'))+'\n')

catalog=[{k:v for k,v in t.items() if k!='scene'} for t in themes]
(OUT/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
(ROOT/'app'/'themes.js').write_text('/* Generated by scripts/build-themes.py. Local assets only. */\nwindow.CommercialBreakThemes = '+json.dumps(themes,separators=(',',':'))+';\n')
print('Generated',len(themes),'themes; max scene objects',max(len(t['scene']['objects']) for t in themes))
