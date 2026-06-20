"""Create standalone single-slide PPTX — 6. Parametric Study."""
import zipfile
from pathlib import Path

OUT = Path(r"C:\Users\Adar\Desktop\robotics assignment\parametric_study.pptx")

MARGIN  = 457200
CARD_W  = 4160520
GAP     = 182880
CARD2_X = MARGIN + CARD_W + GAP

ROW1_Y  = 1280160
ROW2_Y  = 3200400
CARD_H  = 1828800
HEADER_H = 411480
BODY_X_OFF = 182880
BODY_Y_OFF = HEADER_H + 91440

BLUE  = "0071E3"
TEAL  = "30B0C7"
ORG   = "FF9500"
GRN   = "34C759"
DARK  = "1D1D1F"
MID   = "6E6E73"
WHITE = "FFFFFF"

_id = [40]
def nid():
    _id[0] += 1
    return _id[0]

def card_bg(x, y):
    i = nid()
    return f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="{i}" name="CardBg{i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{CARD_W}" cy="{CARD_H}"/></a:xfrm>
    <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 3000"/></a:avLst></a:prstGeom>
    <a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>
    <a:ln w="12700"><a:solidFill><a:srgbClr val="D1D1D6"/></a:solidFill></a:ln>
    <a:effectLst><a:outerShdw blurRad="101600" dist="25400" dir="2700000" algn="bl" rotWithShape="0">
      <a:srgbClr val="000000"><a:alpha val="8000"/></a:srgbClr>
    </a:outerShdw></a:effectLst>
  </p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
</p:sp>"""

def card_header(x, y, color, title):
    i = nid(); j = nid()
    return f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="{i}" name="Hdr{i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{CARD_W}" cy="{HEADER_H}"/></a:xfrm>
    <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 5000"/></a:avLst></a:prstGeom>
    <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
    <a:ln w="0"><a:noFill/></a:ln>
  </p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
</p:sp>
<p:sp>
  <p:nvSpPr><p:cNvPr id="{j}" name="HdrTxt{j}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{CARD_W}" cy="{HEADER_H}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln/>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" lIns="91440" tIns="0" rIns="91440" bIns="0" rtlCol="0" anchor="ctr"/>
    <a:lstStyle/>
    <a:p><a:pPr marL="0" indent="0" algn="ctr"><a:buNone/></a:pPr>
      <a:r><a:rPr lang="en-US" sz="1300" b="1" dirty="0">
        <a:solidFill><a:srgbClr val="{WHITE}"/></a:solidFill>
        <a:latin typeface="Calibri" pitchFamily="34" charset="0"/>
      </a:rPr><a:t>{title}</a:t></a:r></a:p>
  </p:txBody>
</p:sp>"""

def card_bullets(x, y, bullets):
    i = nid()
    bx = x + BODY_X_OFF
    by = y + BODY_Y_OFF
    bw = CARD_W - BODY_X_OFF * 2
    bh = CARD_H - BODY_Y_OFF - 60960
    paras = "".join(f"""<a:p><a:pPr marL="0" indent="0"><a:buNone/></a:pPr>
      <a:r><a:rPr lang="en-US" sz="1000" dirty="0">
        <a:solidFill><a:srgbClr val="{MID}"/></a:solidFill>
        <a:latin typeface="Calibri" pitchFamily="34" charset="0"/>
      </a:rPr><a:t>· {b}</a:t></a:r></a:p>""" for b in bullets)
    return f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="{i}" name="Body{i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{bx}" y="{by}"/><a:ext cx="{bw}" cy="{bh}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln/>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0" anchor="t"/>
    <a:lstStyle/>{paras}
  </p:txBody>
</p:sp>"""

def title_box(i, x, y, w, h, sz, bold, color, face, text):
    b = ' b="1"' if bold else ""
    return f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="{i}" name="Txt{i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln/>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" rtlCol="0" anchor="ctr"/>
    <a:lstStyle/>
    <a:p><a:pPr marL="0" indent="0"><a:buNone/></a:pPr>
      <a:r><a:rPr lang="en-US" sz="{sz}"{b} dirty="0">
        <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
        <a:latin typeface="{face}" pitchFamily="34" charset="0"/>
      </a:rPr><a:t>{text}</a:t></a:r>
    </a:p>
  </p:txBody>
</p:sp>"""

shapes = []
shapes.append(title_box(2, MARGIN, 274320, 8229600, 594360, 3200, True,  DARK, "Cambria", "6. Parametric Study"))
shapes.append(title_box(3, MARGIN, 822960, 8229600, 320040, 1300, False, MID,  "Calibri",
    "How grid size, simulation speed, and planner choice affect navigation KPIs"))

shapes.append(card_bg(MARGIN,  ROW1_Y))
shapes.append(card_header(MARGIN,  ROW1_Y, BLUE, "Planner: A* vs Dijkstra"))
shapes.append(card_bullets(MARGIN, ROW1_Y, [
    "A* uses a heuristic to prune the search space — reaches goal faster",
    "Dijkstra expands all nodes equally — guaranteed optimal but slower",
    "Both achieve 100% solve rate on 120 held-out seeds",
    "A* preferred for real-time systems with large maps",
]))

shapes.append(card_bg(CARD2_X, ROW1_Y))
shapes.append(card_header(CARD2_X, ROW1_Y, TEAL, "Simulation Speed"))
shapes.append(card_bullets(CARD2_X, ROW1_Y, [
    "SPEED multiplier controls sim time vs wall-clock time (default: 2×)",
    "Higher speed → faster batch runs, same navigation quality",
    "Navigation KPIs measured in sim time — speed-independent",
    "Demo mode uses 2× by default (demo.bat 42)",
]))

shapes.append(card_bg(MARGIN,  ROW2_Y))
shapes.append(card_header(MARGIN,  ROW2_Y, ORG, "Grid Resolution"))
shapes.append(card_bullets(MARGIN, ROW2_Y, [
    "Occupancy grid cell size controls map fidelity and path accuracy",
    "Default: 0.15 m per cell — matched to robot footprint + safety buffer",
    "Finer grid → more accurate paths, higher memory and compute cost",
    "30 cm wall buffer inflated into every occupied cell",
]))

shapes.append(card_bg(CARD2_X, ROW2_Y))
shapes.append(card_header(CARD2_X, ROW2_Y, GRN, "Key Findings"))
shapes.append(card_bullets(CARD2_X, ROW2_Y, [
    "A* reduces planning time vs Dijkstra with no loss in path quality",
    "Sim speed does not affect solve rate or path efficiency metrics",
    "Grid resolution is the main lever for wall clearance vs speed trade-off",
    "All parameter combinations maintained 100% solve rate",
]))

slide_xml = f'''<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld name="6. Parametric Study">
    <p:bg><p:bgPr>
      <a:solidFill><a:srgbClr val="F5F5F7"/></a:solidFill>
      <a:effectLst/>
    </p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      {"".join(shapes)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''

# ── pack using same skeleton as make_exec_slide.py ───────────────────────────
files = {
"[Content_Types].xml": """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml"  ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml"
    ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/theme/theme1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>""",
"_rels/.rels": """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>""",
"ppt/presentation.xml": """<?xml version="1.0" encoding="utf-8"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
  <p:sldSz cx="9144000" cy="5143500" type="screen16x9"/>
  <p:notesSz cx="5143500" cy="9144000"/>
</p:presentation>""",
"ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
</Relationships>""",
"ppt/slides/slide1.xml": slide_xml,
"ppt/slides/_rels/slide1.xml.rels": """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>""",
"ppt/slideLayouts/slideLayout1.xml": """<?xml version="1.0" encoding="utf-8"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
      <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
  </p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>""",
"ppt/slideLayouts/_rels/slideLayout1.xml.rels": """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>""",
"ppt/slideMasters/slideMaster1.xml": """<?xml version="1.0" encoding="utf-8"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
    </p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1"
    accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5"
    accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle><a:lvl1pPr><a:defRPr lang="en-US"/></a:lvl1pPr></p:titleStyle>
    <p:bodyStyle><a:lvl1pPr><a:defRPr lang="en-US"/></a:lvl1pPr></p:bodyStyle>
    <p:otherStyle><a:lvl1pPr><a:defRPr lang="en-US"/></a:lvl1pPr></p:otherStyle>
  </p:txStyles>
</p:sldMaster>""",
"ppt/slideMasters/_rels/slideMaster1.xml.rels": """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>""",
"ppt/theme/theme1.xml": """<?xml version="1.0" encoding="utf-8"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office Theme">
  <a:themeElements>
    <a:clrScheme name="Office">
      <a:dk1><a:sysClr lastClr="000000" val="windowText"/></a:dk1>
      <a:lt1><a:sysClr lastClr="ffffff" val="window"/></a:lt1>
      <a:dk2><a:srgbClr val="1F3864"/></a:dk2>
      <a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>
      <a:accent1><a:srgbClr val="0071E3"/></a:accent1>
      <a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
      <a:accent3><a:srgbClr val="A9D18E"/></a:accent3>
      <a:accent4><a:srgbClr val="FFC000"/></a:accent4>
      <a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>
      <a:accent6><a:srgbClr val="70AD47"/></a:accent6>
      <a:hlink><a:srgbClr val="0563C1"/></a:hlink>
      <a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office">
      <a:majorFont><a:latin typeface="Cambria"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>""",
}

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for name, content in files.items():
        zf.writestr(name, content.encode("utf-8"))

print(f"Saved: {OUT}")
