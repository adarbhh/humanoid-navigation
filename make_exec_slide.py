"""Standalone single-slide Executive Summary — metrics card style."""
import zipfile
from pathlib import Path

OUT = Path(r"C:\Users\Adar\Desktop\robotics assignment\executive_summary.pptx")

BLUE  = "0071E3"
DARK  = "1D1D1F"
GRAY  = "6E6E73"
WHITE = "FFFFFF"
BG    = "F5F5F7"
LBLUE = "C8E0FF"

def rr(id_, name, x, y, w, h, fill):
    return f"""<p:sp>
        <p:nvSpPr><p:cNvPr id="{id_}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 8000"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>
          <a:ln w="0"><a:noFill/></a:ln>
        </p:spPr>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
      </p:sp>"""

def tb(id_, name, x, y, w, h, anchor, runs):
    paras = []
    for sz, bold, color, face, align, text in runs:
        b = ' b="1"' if bold else ""
        paras.append(f"""<a:p><a:pPr marL="0" indent="0" algn="{align}"><a:buNone/></a:pPr>
            <a:r><a:rPr lang="en-US" sz="{sz}"{b} dirty="0">
              <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
              <a:latin typeface="{face}" pitchFamily="34" charset="0"/>
            </a:rPr><a:t>{text}</a:t></a:r></a:p>""")
    return f"""<p:sp>
        <p:nvSpPr><p:cNvPr id="{id_}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:noFill/><a:ln/>
        </p:spPr>
        <p:txBody><a:bodyPr wrap="square" rtlCol="0" anchor="{anchor}"/>
          <a:lstStyle/>{"".join(paras)}</p:txBody>
      </p:sp>"""

def stat_card(id_, x, y, w, h, value, label, sublabel):
    return (
        rr(id_, f"Bg{id_}", x, y, w, h, WHITE) +
        tb(id_+1, f"Val{id_}", x, y+91440, w, 548640, "ctr",
           [(4400, True, BLUE, "Cambria", "ctr", value)]) +
        tb(id_+2, f"Lbl{id_}", x, y+685800, w, 274320, "t",
           [(1100, True,  DARK, "Calibri", "ctr", label),
            (900,  False, GRAY, "Calibri", "ctr", sublabel)])
    )

def bottom_card(id_, x, y, w, h, label, body):
    return (
        rr(id_, f"BC{id_}", x, y, w, h, WHITE) +
        tb(id_+1, f"BL{id_}", x+182880, y+137160, w-365760, 228600, "ctr",
           [(900, True, BLUE, "Calibri", "l", label)]) +
        tb(id_+2, f"BB{id_}", x+182880, y+411480, w-365760, h-548640, "t",
           [(950, False, DARK, "Calibri", "l", body)])
    )

# Layout
M    = 457200
W    = 8229600
CW4  = (W - 3*91440) // 4
GAP4 = 91440
xs4  = [M + i*(CW4+GAP4) for i in range(4)]

CW2  = (W - 182880) // 2
C2   = M + CW2 + 182880

STAT_Y = 1005840
STAT_H = 1097280
BOT_Y  = 2194560
BOT_H  = 822960

# Blue accent bar left of objective
OBJ_Y  = 685800
OBJ_H  = 228600

slide = f"""<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="{BG}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>

      {tb(2,"Title",M,182880,W,457200,"ctr",
          [(3600,True,DARK,"Cambria","l","Executive Summary")])}

      {tb(3,"Sub",M,640080,W,228600,"ctr",
          [(1100,False,GRAY,"Calibri","l",
            "Unitree G1 humanoid robot  —  autonomous maze navigation  —  robotics ops engineer assignment")])}

      {stat_card(10, xs4[0], STAT_Y, CW4, STAT_H, "100%",  "Solve Rate",         "120 / 120 held-out seeds")}
      {stat_card(20, xs4[1], STAT_Y, CW4, STAT_H, "2.2 cm","Localization Error",  "Sensor-only, no GPS")}
      {stat_card(30, xs4[2], STAT_Y, CW4, STAT_H, "0",     "Stuck Events",        "Across all 25 runs")}
      {stat_card(40, xs4[3], STAT_Y, CW4, STAT_H, "84%",   "Path Efficiency",     "vs. optimal route")}

      {bottom_card(50, M,   BOT_Y, CW2, BOT_H,
                   "WHAT WAS BUILT",
                   "One-command MuJoCo setup  ·  seeded maze generator  ·  sensor-only navigation stack  ·  crash-safe multi-stream recorder  ·  25-seed KPI report with 95% confidence intervals")}

      {bottom_card(60, C2,  BOT_Y, CW2, BOT_H,
                   "STRETCH GOALS COMPLETED",
                   "Live KPI dashboard  ·  A* vs. Dijkstra comparison  ·  sensor fault injection (locked knee)  ·  second G1 robot as dynamic obstacle with real-time re-routing")}

      {rr(70,"VerdBg",M,3108960,W,457200+182880,BLUE)}
      {tb(71,"VerdTx",M,3108960,W,640080,"ctr",
          [(1200,True,  WHITE,"Calibri","ctr","The system solved every maze it was given — autonomously, without any ground-truth position data."),
           (950, False, LBLUE,"Calibri","ctr","All assignment requirements met  ·  All stretch goals completed  ·  Dataset validated across 25 unseen environments")])}

    </p:spTree>
  </p:cSld>
</p:sld>"""

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
"ppt/slides/slide1.xml": slide,
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

print("Created:", OUT)
