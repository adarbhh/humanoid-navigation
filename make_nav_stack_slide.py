"""Replace/add corrected Navigation Stack slide in parametric_study.pptx."""
import zipfile, shutil
from pathlib import Path

SRC = Path(r"C:\Users\Adar\Desktop\robotics assignment\parametric_study.pptx")
OUT = Path(r"C:\Users\Adar\Desktop\robotics assignment\parametric_study.pptx")
TMP = Path(r"C:\Users\Adar\Desktop\robotics assignment\_nav_tmp")
REPLACE_SLIDE = "ppt/slides/slide2.xml"  # replace existing slide 2

# ── Slide XML ─────────────────────────────────────────────────────────────────
SLIDE_XML = r"""<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>

      <!-- ── Background rect (light grey) ────────────────────────────── -->
      <p:sp><p:nvSpPr><p:cNvPr id="20" name="bg"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="9144000" cy="5143500"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="F5F5F7"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>

      <!-- ── Title ────────────────────────────────────────────────────── -->
      <p:sp><p:nvSpPr><p:cNvPr id="2" name="title"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="457200" y="220000"/><a:ext cx="8229600" cy="560000"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
        <p:txBody><a:bodyPr anchor="ctr"/><a:lstStyle/>
          <a:p><a:pPr algn="l"/>
            <a:r><a:rPr lang="en-US" sz="3200" b="1" dirty="0"><a:solidFill><a:srgbClr val="1D1D1F"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr>
              <a:t>3. Navigation Stack</a:t></a:r></a:p></p:txBody></p:sp>

      <!-- ── Warning banner ───────────────────────────────────────────── -->
      <p:sp><p:nvSpPr><p:cNvPr id="3" name="warn_bg"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="457200" y="820000"/><a:ext cx="8229600" cy="330000"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="FFF3CD"/></a:solidFill>
          <a:ln w="18000"><a:solidFill><a:srgbClr val="E6A817"/></a:solidFill></a:ln></p:spPr>
        <p:txBody><a:bodyPr anchor="ctr" lIns="120000" rIns="120000"/><a:lstStyle/>
          <a:p><a:pPr algn="l"/>
            <a:r><a:rPr lang="en-US" sz="1100" b="1" dirty="0"><a:solidFill><a:srgbClr val="7A4F01"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr>
              <a:t>Hard Rule: Navigation may NOT consume MuJoCo ground-truth pose — closed-loop on own sensing only. They will check.</a:t></a:r></a:p></p:txBody></p:sp>

      <!-- ══════════════════════════════════════════════════════════════ -->
      <!-- COLUMN 1 — PERCEIVE (blue #2563EB) -->
      <!-- ══════════════════════════════════════════════════════════════ -->
      <p:sp><p:nvSpPr><p:cNvPr id="10" name="c1hdr"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="457200" y="1260000"/><a:ext cx="2600000" cy="340000"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 16667"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="2563EB"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>
        <p:txBody><a:bodyPr anchor="ctr"/><a:lstStyle/>
          <a:p><a:pPr algn="ctr"/>
            <a:r><a:rPr lang="en-US" sz="1800" b="1" dirty="0"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr>
              <a:t>Perceive</a:t></a:r></a:p></p:txBody></p:sp>

      <p:sp><p:nvSpPr><p:cNvPr id="11" name="c1body"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="457200" y="1650000"/><a:ext cx="2600000" cy="3100000"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 8333"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>
          <a:ln w="12000"><a:solidFill><a:srgbClr val="DBEAFE"/></a:solidFill></a:ln></p:spPr>
        <p:txBody><a:bodyPr anchor="t" lIns="160000" rIns="120000" tIns="180000"/><a:lstStyle/>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>16-ray 270 deg LiDAR ring</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Occupancy grid mapping</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>IMU gyro orientation</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Joint state feedback</a:t></a:r></a:p>
        </p:txBody></p:sp>

      <!-- ══════════════════════════════════════════════════════════════ -->
      <!-- COLUMN 2 — PLAN (teal #0D9488) -->
      <!-- ══════════════════════════════════════════════════════════════ -->
      <p:sp><p:nvSpPr><p:cNvPr id="12" name="c2hdr"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="3272000" y="1260000"/><a:ext cx="2600000" cy="340000"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 16667"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="0D9488"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>
        <p:txBody><a:bodyPr anchor="ctr"/><a:lstStyle/>
          <a:p><a:pPr algn="ctr"/>
            <a:r><a:rPr lang="en-US" sz="1800" b="1" dirty="0"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr>
              <a:t>Plan</a:t></a:r></a:p></p:txBody></p:sp>

      <p:sp><p:nvSpPr><p:cNvPr id="13" name="c2body"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="3272000" y="1650000"/><a:ext cx="2600000" cy="3100000"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 8333"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>
          <a:ln w="12000"><a:solidFill><a:srgbClr val="CCFBF1"/></a:solidFill></a:ln></p:spPr>
        <p:txBody><a:bodyPr anchor="t" lIns="160000" rIns="120000" tIns="180000"/><a:lstStyle/>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Dead-reckoning localisation (IMU + odometry)</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>BFS path planning (maze solution)</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>A* / Dijkstra / Weighted A* (benchmarked)</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Wall-centering cost via distance transform</a:t></a:r></a:p>
        </p:txBody></p:sp>

      <!-- ══════════════════════════════════════════════════════════════ -->
      <!-- COLUMN 3 — MOVE (green #16A34A) -->
      <!-- ══════════════════════════════════════════════════════════════ -->
      <p:sp><p:nvSpPr><p:cNvPr id="14" name="c3hdr"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="6086800" y="1260000"/><a:ext cx="2600000" cy="340000"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 16667"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="16A34A"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>
        <p:txBody><a:bodyPr anchor="ctr"/><a:lstStyle/>
          <a:p><a:pPr algn="ctr"/>
            <a:r><a:rPr lang="en-US" sz="1800" b="1" dirty="0"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr>
              <a:t>Move</a:t></a:r></a:p></p:txBody></p:sp>

      <p:sp><p:nvSpPr><p:cNvPr id="15" name="c3body"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="6086800" y="1650000"/><a:ext cx="2600000" cy="3100000"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 8333"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>
          <a:ln w="12000"><a:solidFill><a:srgbClr val="DCFCE7"/></a:solidFill></a:ln></p:spPr>
        <p:txBody><a:bodyPr anchor="t" lIns="160000" rIns="120000" tIns="180000"/><a:lstStyle/>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Pure-pursuit waypoint following</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Velocity commands to walking policy</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Kinematic freejoint locomotion</a:t></a:r></a:p>
          <a:p><a:pPr algn="l" indent="-200000" marL="200000"/>
            <a:r><a:rPr lang="en-US" sz="1300" dirty="0"><a:solidFill><a:srgbClr val="3C3C43"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Smooth heading transitions (cos^2 blend)</a:t></a:r></a:p>
        </p:txBody></p:sp>

    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""

# ── Read existing PPTX and replace slide 2 ────────────────────────────────────
import re

with zipfile.ZipFile(SRC, 'r') as zin:
    names = zin.namelist()
    files = {n: zin.read(n) for n in names}

# Replace slide 2 in place — no registration changes needed
files[REPLACE_SLIDE] = SLIDE_XML.encode("utf-8")

# Write output
TMP.unlink(missing_ok=True)
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as zout:
    for name, data in files.items():
        zout.writestr(name, data)

print(f"Done — updated slide 2 in {OUT}")
