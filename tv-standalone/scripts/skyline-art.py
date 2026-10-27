"""Original vector skyline compositions. Geographic landmark profiles, not photos."""
import math

def city_scenes(base,rect,ellipse,poly,line,add):
    for city,label,description in [
        ('raleigh','Raleigh','PNC’s spire, the stepped Wells Fargo tower and Raleigh’s downtown roofline.'),
        ('memphis','Memphis','The Pyramid, Hernando de Soto Bridge and the Mississippi riverfront.'),
        ('dc','Washington, DC','The Capitol dome, Washington Monument and Lincoln Memorial.'),
        ('charlotte','Charlotte','The Corporate Center’s crown, angular 550 South Tryon and Uptown towers.')]:
      for night in [False,True]:
        mode='night' if night else 'day'
        if night: sky=('#111E30','#3D5262'); back='#465A6A';front='#203444';side='#2A4051';detail='#87998F';ground='#162A38';sun='#D8DCD5'
        else: sky=('#324D61','#8FA2A6');back='#687F89';front='#3E5967';side='#4B6875';detail='#8EA4A7';ground='#304C5A';sun='#E3C999'
        o=base(*sky)
        o += [ellipse(1480,155,150,150,sun)]
        # Deliberately still, sparse sky. These are vector stars, not animation.
        if night:
          for x,y in [(228,180),(386,280),(1120,205),(1728,360),(1740,138)]:o.append(ellipse(x,y,3,3,'#A7B4B8'))
        art_start=len(o)
        def block(x,y,w,h,c=front):o.append(rect(x,y,w,h,c))
        def shape(pts,c=front):o.append(poly(pts,c))
        def windows(x,y,w,h,cols=3,rows=6):
          # Restrained vertical facade rhythm keeps the silhouette dominant.
          for col in range(cols):
            xx=x+7+(w-14)*col/max(1,cols-1)
            if night:
              for row in range(rows):
                if (col*3+row*5)%4!=0: o.append(rect(round(xx),round(y+row*h/rows),3,5,detail))
            else:o.append(rect(round(xx),y,2,h,detail))
        def lowrise(items,c=back):
          for x,w,h in items:block(x,990-h,w,h,c)
        if city=='raleigh':
          # Original landmark composition, viewed from the north: Hanover left,
          # PNC near the center and 150 Fayetteville right. Architectural profiles
          # are simplified independently; this is not a trace of another print.
          lowrise([(120,160,64),(275,125,110),(390,120,144),(635,120,165),(735,110,127),(1070,145,170),(1200,110,140),(1440,120,160),(1540,150,88),(1680,160,48)])
          # Two Hanover Square: paired peaked roof towers, recessed center.
          block(470,698,185,312,side)
          block(470,709,62,301);block(593,709,62,301)
          shape([(466,709),(501,662),(536,709)])
          shape([(589,709),(624,662),(659,709)])
          block(530,678,66,11);block(557,688,11,322,front)
          windows(481,733,37,230,2,5);windows(604,733,37,230,2,5)
          # PNC's crown sits over the narrow tall shaft, alongside a lower wing.
          block(894,673,89,337);shape([(983,714),(1100,731),(1100,1010),(983,1010)],side)
          block(887,665,104,12)
          shape([(897,665),(938,595),(981,665)])
          shape([(909,660),(938,610),(968,660)],back)
          o.append(line(938,609,938,659,detail))
          block(936,568,4,31);block(978,680,5,330,detail)
          windows(907,700,56,235,3,6);windows(1004,755,72,191,3,5)
          # 150 Fayetteville: angular, stepped crown and twin vertical shoulders.
          shape([(1290,1010),(1290,728),(1303,728),(1303,705),(1317,705),(1317,682),(1331,682),(1331,659),(1350,659),(1350,636),(1373,636),(1373,654),(1392,654),(1392,676),(1410,676),(1410,699),(1426,699),(1426,724),(1441,724),(1441,1010)])
          shape([(1350,660),(1373,660),(1373,715),(1392,715),(1392,787),(1410,787),(1410,1010),(1384,1010),(1384,812),(1367,812),(1367,741),(1350,741)],side)
          windows(1309,752,37,205,2,6);windows(1406,754,22,202,2,5)
          # Overlapping mid-rise masses create a continuous city rather than
          # evenly spaced freestanding icons. Keep their details restrained.
          block(700,878,129,132);block(716,863,98,15);windows(718,900,84,72,3,3)
          block(811,914,80,96,side);block(1108,873,112,137);block(1121,859,86,14)
          block(1211,927,90,83,side);block(1453,902,95,108)
          lowrise([(270,135,50),(390,114,68),(640,81,66),(856,77,50),(1018,97,53),(1530,125,56)],front)
          # Raleigh is inland: a continuous, irregular green tree line, not
          # broad blue wave-like ellipses or an exposed horizontal water band.
          ground='#1C302C' if night else '#3A554B'
          foliage='#294039' if night else '#50695B'
          canopy=[(0,1080),(0,989)]
          for x in range(0,1921,20):
            y=987+12*math.sin(x*.019)+8*math.sin(x*.057)+5*math.cos(x*.131)
            canopy.append((x,round(y)))
          canopy.append((1920,1080));shape(canopy,ground)
          # Individual upright crowns give the foreground an unmistakable
          # wooded character while leaving the landmark roofs unobstructed.
          for x,y,s in [(160,969,1),(308,952,1.15),(690,970,.85),(1180,966,.9),(1548,951,1.2),(1745,970,.9)]:
            block(round(x+24*s),round(y+32*s),round(5*s),round(60*s),ground)
            o.append(ellipse(x,round(y+18*s),round(53*s),round(50*s),foliage))
            o.append(ellipse(round(x+12*s),round(y-8*s),round(34*s),round(52*s),foliage))
            o.append(ellipse(round(x+29*s),round(y+24*s),round(32*s),round(40*s),foliage))
        elif city=='memphis':
          lowrise([(1010,85,100),(1110,85,160),(1235,70,122),(1350,90,90),(1490,90,130),(1620,75,100),(1720,130,65)],back)
          # North riverbank Pyramid, a distinctive low, wide profile.
          shape([(270,998),(455,730),(642,998)]);shape([(455,730),(642,998),(490,998)],side)
          o.append(line(455,733,490,996,detail))
          # 100 North Main's rooftop pavilion and the slender historic Sterick.
          block(1235,764,104,234);block(1250,747,74,18);block(1265,737,43,10);windows(1250,785,73,178,4,6)
          shape([(1415,998),(1415,812),(1429,812),(1429,786),(1444,786),(1444,762),(1476,762),(1476,786),(1491,786),(1491,812),(1505,812),(1505,998)])
          windows(1434,829,51,140,3,5)
          block(1605,859,96,139);windows(1620,880,65,88,3,4)
          # Hernando de Soto bridge: two continuous M-shaped arches over water.
          for start in [10,470]:
            pts=[]
            for i in range(25):
              t=i/24;pts.append((start+t*460,966-127*math.sin(math.pi*t)))
            pts += [(x,y+9) for x,y in reversed(pts)]
            shape(pts,side)
            for i in range(1,12):
              t=i/12;x=start+t*460;y=966-127*math.sin(math.pi*t);o.append(rect(round(x),round(y+6),3,round(974-y),side))
          block(0,975,980,12,front)
          for x in [13,469,927]:block(x,985,13,58,front)
          block(970,986,950,42,ground)
          block(0,1030,1920,50,ground)
          for x,y,w in [(75,1044,290),(510,1055,240),(980,1043,110),(1340,1063,230)]:block(x,y,w,2,side)
        elif city=='dc':
          # Low horizontal city, with the great public monuments above it.
          lowrise([(0,190,55),(205,120,75),(420,150,47),(650,145,70),(840,125,58),(1040,130,74),(1710,210,65)],back)
          # Lincoln Memorial: classical pediment, broad entablature, colonnade.
          block(120,915,240,90);block(107,902,266,14);shape([(109,902),(240,874),(371,902)])
          for x in range(137,350,29):block(x,925,13,65,side)
          block(108,1001,266,9);block(97,1010,288,9)
          # Washington Monument: one unmistakably slender obelisk.
          shape([(671,1015),(681,720),(699,686),(717,720),(727,1015)]);shape([(699,686),(717,720),(727,1015),(699,1015)],side)
          # Capitol: wings and colonnaded drum beneath a curved dome and lantern.
          block(1210,919,465,96);block(1185,1006,515,12);block(1275,905,336,15)
          block(1379,853,127,66);block(1367,847,151,11)
          dome=[(1382,847)]+[(1442+61*math.cos(math.pi+i*math.pi/24),847+98*math.sin(math.pi+i*math.pi/24)) for i in range(25)]+[(1503,847)]
          shape(dome);block(1428,741,28,13);block(1434,724,16,19);shape([(1433,724),(1442,708),(1451,724)]);block(1441,693,3,17)
          for x in range(1390,1503,18):block(x,863,7,41,side)
          for x in list(range(1230,1372,22))+list(range(1523,1667,22)):block(x,938,6,55,side)
          block(0,1021,1920,59,ground)
        else:
          lowrise([(0,110,75),(115,120,110),(245,115,90),(470,110,160),(600,100,100),(835,104,120),(960,100,175),(1170,95,120),(1445,100,120),(1580,100,110),(1700,220,60)],back)
          # 550 South Tryon (former Duke Energy Center): sloping cutout crown.
          shape([(320,1000),(320,754),(334,706),(447,655),(447,1000)])
          shape([(338,739),(352,713),(429,681),(429,698)],back)
          block(439,660,5,340,side);windows(339,767,81,190,4,7)
          # Bank of America Corporate Center: setbacks and open, radiating crown.
          shape([(742,1000),(742,786),(750,786),(750,752),(761,752),(761,720),(772,720),(772,697),(784,697),(784,678),(796,678),(796,663),(866,663),(866,678),(879,678),(879,697),(891,697),(891,720),(902,720),(902,752),(913,752),(913,786),(921,786),(921,1000)])
          shape([(794,663),(803,643),(813,625),(831,603),(849,625),(859,643),(869,663)],side)
          for x in [801,812,824,838,850,862]:o.append(line(x,661,831,604,detail))
          block(827,592,5,13,front);windows(770,796,122,170,5,7)
          # One Wells Fargo's rounded shoulder, and a pyramidal Legacy Union roof.
          block(1066,805,128,195);o.append(ellipse(1066,767,128,78,front));block(1091,813,84,187,side);windows(1085,836,84,130,4,5)
          block(1324,830,135,170);shape([(1324,830),(1392,755),(1459,830)]);shape([(1392,755),(1459,830),(1392,830)],side);block(1317,831,149,9);windows(1342,854,96,112,4,5)
          lowrise([(205,140,70),(448,120,65),(610,110,89),(931,115,50),(1190,125,83),(1466,130,60)],front)
          block(0,1015,1920,65,ground)
        if city=='raleigh':o.append(rect(0,1050,1920,30,ground))
        # Keep even the tallest spire comfortably below the subtitle.
        for obj in o[art_start:]:
          if obj['type'] in ('rectangle','ellipse'):
            obj['y']=round(1080+(obj['y']-1080)*.85)
            obj['height']=max(1,round(obj['height']*.85))
          elif obj['type']=='polygon':
            for pt in obj['points']:pt['y']=round(1080+(pt['y']-1080)*.85)
          elif obj['type']=='line':
            for key in ('y1','y2'):obj[key]=round(1080+(obj[key]-1080)*.85)
        add(city+'-'+mode,label+' · '+mode.title(),'City skylines',description,o)
