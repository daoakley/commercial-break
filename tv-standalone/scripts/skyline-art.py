"""Original vector landmark compositions with shared day/night geometry.

Simplified, not a surveyed panorama. Buildings stand on land; bridges cross
water. Coordinates are final screen coordinates, without vertical-only scaling.
"""
import math


def city_scenes(base, rect, ellipse, poly, line, add):
    cities = [
        ('raleigh', 'Raleigh', 'PNC Plaza’s open crown, stepped 150 Fayetteville and a wooded foreground.'),
        ('memphis', 'Memphis', 'The Pyramid on the riverbank, with the M Bridge crossing the Mississippi in front.'),
        ('dc', 'Washington, DC', 'The Lincoln Memorial, slender Washington Monument and Capitol dome.'),
        ('charlotte', 'Charlotte', 'Uptown’s glass pyramidal roof, angular 550 South Tryon and Corporate Center crown.')]
    for city, label, description in cities:
      for night in (False, True):
        mode = 'night' if night else 'day'
        if night:
            sky = ('#111E30', '#3D5262')
            back, front, side, detail, ground, sun = '#465A6A', '#203444', '#2A4051', '#87998F', '#162A38', '#D8DCD5'
        else:
            sky = ('#324D61', '#8FA2A6')
            back, front, side, detail, ground, sun = '#687F89', '#3E5967', '#4B6875', '#8EA4A7', '#304C5A', '#E3C999'
        foliage = '#294039' if night else '#50695B'
        o = base(*sky) + [ellipse(1480, 155, 150, 150, sun)]
        if night:
            for x, y in [(228, 180), (386, 280), (1120, 205), (1728, 360), (1740, 138)]:
                o.append(ellipse(x, y, 3, 3, '#A7B4B8'))

        def block(x, y, w, h, c=front):
            o.append(rect(x, y, w, h, c))

        def shape(points, c=front):
            o.append(poly(points, c))

        def stroke(x, y, xx, yy, c=detail):
            o.append(line(x, y, xx, yy, c))

        def windows(x, y, w, h, cols=3, rows=4):
            for col in range(cols):
                xx = round(x + 7 + (w - 14) * col / max(1, cols - 1))
                if night:
                    for row in range(rows):
                        if (col * 3 + row * 5) % 4 != 0:
                            block(xx, round(y + row * h / rows), 3, 5, detail)
                else:
                    block(xx, y, 2, h, detail)

        def lowrise(items, c=back, baseline=1015):
            for x, w, h in items:
                block(x, baseline - h, w, h, c)

        if city == 'raleigh':
            lowrise([(120, 160, 64), (275, 125, 95), (390, 120, 128), (635, 120, 145),
                     (735, 110, 112), (1100, 145, 147), (1200, 110, 122), (1440, 120, 139), (1540, 150, 77), (1680, 160, 48)])
            # Two Hanover Square: twin peaked shoulders and a recessed center.
            block(470, 767, 160, 248, side)
            block(470, 773, 55, 242); block(575, 773, 55, 242)
            shape([(466, 773), (497, 730), (529, 773)])
            shape([(571, 773), (602, 730), (634, 773)])
            block(524, 747, 53, 10); block(547, 757, 8, 258)
            windows(480, 794, 35, 172, 2); windows(585, 794, 35, 172, 2)
            # PNC is a broad glass slab. Its taller end carries an open crown;
            # the adjoining upper facade is only slightly lower, not a low wing.
            block(880, 757, 194, 258)
            shape([(1074, 757), (1114, 746), (1114, 1015), (1074, 1015)], side)
            block(1036, 730, 78, 285, side); block(1029, 722, 92, 10)
            for dx in (0, 15, 30, 45, 60, 75):
                stroke(1037 + dx, 721, 1074 + (dx - 37) * .12, 674)
            stroke(1035, 722, 1074, 668); stroke(1115, 722, 1074, 668)
            block(1072, 651, 3, 24)
            windows(894, 779, 127, 188, 5); windows(1047, 749, 53, 218, 3)
            # 150 Fayetteville's stepped masonry crown and vertical shoulders.
            shape([(1288, 1015), (1288, 804), (1301, 804), (1301, 783), (1315, 783),
                   (1315, 765), (1332, 765), (1332, 747), (1350, 747), (1350, 734),
                   (1372, 734), (1372, 751), (1390, 751), (1390, 773), (1405, 773),
                   (1405, 794), (1420, 794), (1420, 1015)])
            shape([(1350, 751), (1372, 751), (1372, 801), (1390, 801), (1390, 849),
                   (1405, 849), (1405, 1015), (1383, 1015), (1383, 867), (1367, 867),
                   (1367, 817), (1350, 817)], side)
            windows(1302, 823, 36, 143, 2); windows(1394, 826, 18, 140, 2)
            lowrise([(270, 135, 50), (390, 114, 68), (640, 81, 66), (715, 120, 117),
                     (820, 70, 78), (1120, 112, 123), (1220, 75, 68), (1453, 95, 99), (1530, 125, 56)], front)
            ground = '#1C302C' if night else '#3A554B'
            canopy = [(0, 1080), (0, 1008)]
            for x in range(0, 1921, 20):
                y = 1007 + 9 * math.sin(x * .019) + 6 * math.sin(x * .057) + 4 * math.cos(x * .131)
                canopy.append((x, round(y)))
            shape(canopy + [(1920, 1080)], ground)
            for x, y, s in [(160, 995, 1), (308, 983, 1.1), (690, 997, .85),
                            (1180, 994, .9), (1548, 981, 1.15), (1745, 997, .9)]:
                o.append(ellipse(x, y, round(48 * s), round(34 * s), foliage))
                o.append(ellipse(round(x + 13 * s), round(y - 18 * s), round(29 * s), round(43 * s), foliage))

        elif city == 'memphis':
            # Three planes: city on the far bank, river in front, and bridge
            # crossing from the left. No bridge crosses the Pyramid footprint.
            lowrise([(1120, 85, 74), (1220, 70, 110), (1350, 90, 80),
                     (1490, 90, 103), (1620, 75, 81), (1720, 130, 58)], baseline=956)
            block(1242, 756, 94, 200); block(1254, 744, 70, 14); block(1268, 736, 42, 9)
            windows(1256, 776, 66, 142, 4)
            shape([(1425, 956), (1425, 809), (1438, 809), (1438, 787), (1452, 787),
                   (1452, 768), (1479, 768), (1479, 787), (1494, 787), (1494, 809),
                   (1507, 809), (1507, 956)])
            windows(1441, 826, 51, 102, 3)
            block(1610, 839, 91, 117); windows(1623, 857, 63, 70, 3)
            block(0, 956, 1920, 124, ground)
            # A visible base well inland of the waterline, separate from the
            # bridge abutment. The Pyramid stands on land, not on the bridge.
            shape([(850, 950), (1010, 740), (1170, 950)])
            shape([(1010, 740), (1170, 950), (1040, 950)], side)
            stroke(1010, 743, 1040, 947); block(846, 950, 328, 9, side)
            bank = '#233C35' if night else '#506458'
            shape([(660, 985), (785, 956), (1920, 956), (1920, 1018), (765, 1018), (660, 1002)], bank)
            for x, y, w in [(790, 957, 39), (1190, 954, 48), (1355, 953, 43), (1550, 956, 45), (1765, 952, 51)]:
                o.append(ellipse(x, y, w, 22, foliage))
            shape([(0, 1008), (755, 1008), (885, 1015), (1920, 1015), (1920, 1080), (0, 1080)], ground)
            stroke(880, 1014, 1920, 1014, side)
            # Paired tied-arch trusses, with thickness and diagonal bracing.
            # Both spans end before the Pyramid footprint begins at x=846.
            for start in (-14, 376):
                def arch(t):
                    return 999 - 105 * math.sin(math.pi * t)
                upper = [(start + t * 390, arch(t)) for t in [i / 24 for i in range(25)]]
                shape(upper + [(x, y + 12) for x, y in reversed(upper)], side)
                for i in range(1, 10):
                    t = i / 10
                    x, y = start + t * 390, arch(t)
                    block(round(x), round(y + 12), 3, round(1004 - y - 12), side)
                for i in range(10):
                    t, u = i / 10, (i + 1) / 10
                    stroke(start + t * 390, arch(t) + (12 if i % 2 else 0),
                           start + u * 390, arch(u) + (0 if i % 2 else 12))
            block(0, 1003, 805, 11)
            for x in (4, 372, 762):
                block(x, 1014, 13, 44)
            block(789, 1006, 22, 26, side)
            for x, y, w in [(75, 1045, 230), (440, 1063, 205), (990, 1042, 170), (1380, 1063, 270)]:
                block(x, y, w, 2, side)

        elif city == 'dc':
            lowrise([(0, 155, 48), (405, 135, 50), (565, 100, 43), (860, 125, 48),
                     (1020, 130, 57), (1740, 180, 55)], baseline=1020)
            # Rectangular attic, horizontal entablature and eight front columns.
            block(168, 888, 224, 26); block(158, 914, 244, 13)
            block(170, 927, 220, 67, side)
            for x in range(175, 387, 29):
                block(x, 927, 13, 66)
            block(156, 994, 248, 8); block(146, 1002, 268, 9); block(136, 1011, 288, 9)
            # Approximately 10:1 height/base width: 555 feet tall, 55-foot base.
            shape([(727, 1020), (732, 696), (745, 660), (758, 696), (763, 1020)])
            shape([(745, 660), (758, 696), (763, 1020), (745, 1020)], side)
            block(1230, 954, 420, 61); block(1215, 1013, 450, 7)
            block(1376, 908, 128, 107); block(1366, 901, 148, 9)
            dome = [(1378, 901)] + [(1440 + 62 * math.cos(math.pi + i * math.pi / 24),
                                    901 + 78 * math.sin(math.pi + i * math.pi / 24)) for i in range(25)]
            shape(dome + [(1502, 901)])
            block(1427, 815, 26, 10); block(1433, 799, 14, 17)
            shape([(1431, 799), (1440, 786), (1449, 799)]); block(1439, 775, 3, 13)
            for x in range(1389, 1500, 18):
                block(x, 918, 7, 35, side)
            for x in list(range(1246, 1363, 22)) + list(range(1520, 1639, 22)):
                block(x, 965, 6, 35, side)
            block(0, 1020, 1920, 60, ground)

        else:
            # South-side composition: Legacy Union and 550 South Tryon in
            # front, Corporate Center deeper into Uptown, 301 S College right.
            lowrise([(0, 160, 64), (175, 140, 94), (475, 115, 118), (770, 120, 137),
                     (860, 95, 165), (1110, 95, 156), (1460, 110, 98), (1590, 120, 74), (1740, 180, 60)])
            # Corporate Center's terraced shoulders and tiered upright masts.
            shape([(932, 1015), (932, 766), (942, 766), (942, 745), (953, 745),
                   (953, 731), (965, 731), (965, 722), (1035, 722), (1035, 731),
                   (1047, 731), (1047, 745), (1058, 745), (1058, 766), (1068, 766), (1068, 1015)])
            shape([(965, 722), (965, 686), (977, 670), (990, 660), (1010, 660),
                   (1023, 670), (1035, 686), (1035, 722)], side)
            for x, top in [(965, 680), (977, 662), (989, 651), (1001, 648), (1013, 651), (1025, 662), (1037, 680)]:
                block(x, top, 2, 722 - top, detail)
            stroke(967, 703, 1037, 703); stroke(965, 717, 1039, 717)
            windows(948, 787, 102, 173, 4)
            # Legacy Union: glass pyramid above a horizontal cornice and slab.
            block(330, 822, 124, 193)
            shape([(324, 815), (391, 753), (460, 815)])
            shape([(391, 753), (460, 815), (391, 815)], side)
            block(322, 815, 140, 8); block(329, 862, 126, 6, side)
            windows(341, 881, 101, 90, 4)
            # 550 South Tryon's angled crown has a visible open cutout.
            shape([(594, 1015), (594, 762), (606, 716), (716, 690), (716, 1015)])
            shape([(609, 749), (621, 723), (703, 704), (703, 718)], back)
            block(708, 700, 5, 315, side); windows(608, 782, 87, 182, 4)
            # Rounded barrel roof and narrower vertical face of 301 S College.
            o.append(ellipse(1260, 775, 112, 64, front))
            block(1260, 807, 112, 208); block(1280, 814, 75, 201, side)
            windows(1277, 838, 76, 128, 3)
            lowrise([(235, 100, 62), (455, 128, 83), (720, 120, 112), (855, 85, 67),
                     (1070, 128, 75), (1190, 74, 55), (1380, 116, 87), (1520, 105, 48)], front)
            block(0, 1015, 1920, 65, ground)

        add(city + '-' + mode, label + ' · ' + mode.title(), 'City skylines', description, o)
