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
          # Southern composition: horizontal office mass, terraced tower, PNC spire.
          lowrise([(0,110,55),(98,115,80),(205,90,125),(295,118,95),(438,100,80),(590,115,115),(710,88,85),(900,110,110),(1190,110,100),(1290,180,85),(1490,94,120),(1600,95,70),(1730,190,45)])
          # Two Hanover Square: squared top and narrow vertical ribs.
          block(330,770,115,230);block(342,759,91,12);windows(345,788,85,170,4,5)
          # Progress plaza's long, flat roofline.
          block(485,805,180,195);shape([(485,805),(510,795),(665,795),(665,1000),(485,1000)]);block(505,813,145,6,side)
          windows(508,837,131,130,4,5)
          # Wells Fargo / 150 Fayetteville: broad paired setbacks at the crown.
          shape([(735,1000),(735,779),(745,779),(745,753),(756,753),(756,731),(770,731),(770,709),(786,709),(786,694),(807,694),(807,710),(824,710),(824,694),(843,694),(843,710),(858,710),(858,731),(871,731),(871,753),(882,753),(882,779),(891,779),(891,1000)])
          block(813,775,25,225,side);windows(760,792,108,170,4,7)
          # PNC: offset tall shaft and open triangular crown, thin central mast.
          block(1040,744,146,256);block(1139,713,70,287);block(1131,704,86,10)
          shape([(1141,704),(1174,645),(1206,704)]);shape([(1153,699),(1174,658),(1195,699)],back)
          block(1172,615,3,34,front);block(1150,726,47,12,side);block(1138,744,7,256,side)
          windows(1056,764,66,204,4,8);windows(1151,760,46,205,3,7)
          # Marriott and the lower Fayetteville Street fabric.
          block(1300,846,144,154);block(1313,837,118,9);windows(1320,865,98,100,4,4)
          lowrise([(173,97,57),(475,81,41),(654,102,74),(904,104,62),(1214,85,50),(1460,110,80),(1660,170,60)],front)
          # Raleigh's trees form the base, rather than an invented waterfront.
          for x,y,w in [(0,990,230),(170,1006,280),(420,998,260),(660,1014,340),(980,1002,230),(1220,1008,270),(1450,989,300),(1730,1002,250)]:o.append(ellipse(x,y,w,110,ground))
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
