"""Replace slide 23 with a narrative Executive Summary of the full assignment."""
import sys, zipfile
from pathlib import Path

UNPACKED = Path(r"C:\Users\Adar\Desktop\robotics assignment\unpacked_pptx")
SLIDES   = UNPACKED / "ppt" / "slides"
RELS     = SLIDES / "_rels"
PPTX_OUT = Path(r"C:\Users\Adar\Desktop\robotics assignment\robotics_ops_presentation_with_summary.pptx")

NEW_SLIDE_NUM = 23
NEW_RID       = "rId29"
NEW_SLIDE_ID  = "290"

# ── helpers ───────────────────────────────────────────────────────────────────

def rr(id_, name, x, y, w, h, fill):
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{id_}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 10000"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>
          <a:ln w="0"><a:noFill/></a:ln>
        </p:spPr>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
      </p:sp>"""


def txt_box(id_, name, x, y, w, h, anchor, runs):
    """runs = list of (sz, bold, color, face, align, text)"""
    paras = []
    for sz, bold, color, face, align, text in runs:
        b_attr = ' b="1"' if bold else ""
        paras.append(f"""
          <a:p>
            <a:pPr marL="0" indent="0" algn="{align}"><a:buNone/></a:pPr>
            <a:r>
              <a:rPr lang="en-US" sz="{sz}"{b_attr} dirty="0">
                <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
                <a:latin typeface="{face}" pitchFamily="34" charset="0"/>
              </a:rPr>
              <a:t>{text}</a:t>
            </a:r>
          </a:p>""")
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{id_}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:noFill/><a:ln/>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" rtlCol="0" anchor="{anchor}"/>
          <a:lstStyle/>{"".join(paras)}
        </p:txBody>
      </p:sp>"""


def phase_block(base_id, x, y, w, num, title, body):
    """Blue number chip + bold title + gray body text."""
    CHIP = 228600
    GAP  = 60960
    parts = [
        rr(base_id, f"Chip{base_id}", x, y, CHIP, CHIP, "0071E3"),
        txt_box(base_id+1, f"ChipN{base_id}", x, y, CHIP, CHIP, "ctr",
                [(900, True, "FFFFFF", "Calibri", "ctr", num)]),
        txt_box(base_id+2, f"PhTitle{base_id}", x+CHIP+GAP, y, w-CHIP-GAP, CHIP, "ctr",
                [(1100, True, "1D1D1F", "Calibri", "l", title)]),
        txt_box(base_id+3, f"PhBody{base_id}", x, y+CHIP+GAP, w, 320040, "t",
                [(900, False, "6E6E73", "Calibri", "l", body)]),
    ]
    return "".join(parts)


# ── layout ────────────────────────────────────────────────────────────────────
MARGIN  = 457200
COL_W   = 3886200   # ~2 columns
COL_GAP = 548640
COL2_X  = MARGIN + COL_W + COL_GAP

# Left column: 3 phases stacked
# Right column: 2 phases + outcome box
PH_H    = 640080    # height per phase block (chip + body)
PH_GAP  = 91440
PH_Y0   = 1143000

# 5 phases: 3 left, 2 right
left_ys  = [PH_Y0 + i*(PH_H + PH_GAP) for i in range(3)]
right_ys = [PH_Y0, PH_Y0 + PH_H + PH_GAP]

# Outcome box at bottom-right
OUT_Y = PH_Y0 + 2*(PH_H + PH_GAP)

slide_xml = f'''<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld name="Executive Summary">
    <p:bg>
      <p:bgPr>
        <a:solidFill><a:srgbClr val="F5F5F7"/></a:solidFill>
        <a:effectLst/>
      </p:bgPr>
    </p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>

      {txt_box(2, "Title", MARGIN, 182880, 8229600, 457200, "ctr",
               [(3200, True, "1D1D1F", "Cambria", "l", "Executive Summary")])}

      {txt_box(3, "Subtitle", MARGIN, 640080, 8229600, 274320, "ctr",
               [(1100, False, "6E6E73", "Calibri", "l",
                 "An end-to-end robotics operations pipeline — from simulation environment to validated KPI report — built entirely from scratch.")])}

      {phase_block(10, MARGIN, left_ys[0], COL_W, "1",
                   "Simulation Environment",
                   "Set up the Unitree G1 humanoid robot in MuJoCo with pinned dependencies and a one-command reproducible install. Verified physics fidelity with a smoke-test suite.")}

      {phase_block(20, MARGIN, left_ys[1], COL_W, "2",
                   "Procedural Maze Generator",
                   "Built a seeded maze generator that produces solvable MuJoCo environments with corridors sized for the G1 footprint. Same seed always yields the same maze — guaranteed reproducibility.")}

      {phase_block(30, MARGIN, left_ys[2], COL_W, "3",
                   "Autonomous Navigation Stack",
                   "Implemented LiDAR-based occupancy mapping, IMU dead-reckoning localization, A* global planning, and pure-pursuit control — with no access to simulator ground-truth pose at any point.")}

      {phase_block(40, COL2_X, right_ys[0], COL_W, "4",
                   "Multi-Stream Data Collection",
                   "Recorded IMU, LiDAR, RGB-D camera, and joint state at production quality: 0% frame-drop across all streams, per-sample timestamps, and crash-safe HDF5 files that survive SIGKILL.")}

      {phase_block(50, COL2_X, right_ys[1], COL_W, "5",
                   "KPI Analysis & Stress Testing",
                   "Benchmarked across 120 held-out seeds. Tested sensor-fault resilience (locked knee joint). Compared A* vs. Dijkstra planning. Generated a full statistical KPI report with 95% confidence intervals.")}

      {rr(60, "OutcomeBg", COL2_X, OUT_Y, COL_W, 548640, "0071E3")}
      {txt_box(61, "OutcomeText", COL2_X, OUT_Y, COL_W, 548640, "ctr",
               [(1100, True,  "FFFFFF", "Calibri", "ctr", "Result: 100% solve rate across all 25 unseen mazes."),
                (900,  False, "C8E0FF", "Calibri", "ctr", "Fully autonomous  ·  No ground-truth pose  ·  Zero stuck events")])}
    </p:spTree>
  </p:cSld>
</p:sld>'''

# ── write slide23.xml (overwrite) ─────────────────────────────────────────────
(SLIDES / f"slide{NEW_SLIDE_NUM}.xml").write_text(slide_xml, encoding="utf-8")
print(f"Wrote slide{NEW_SLIDE_NUM}.xml")

# ── ensure rels exists ────────────────────────────────────────────────────────
rels_path = RELS / f"slide{NEW_SLIDE_NUM}.xml.rels"
if not rels_path.exists():
    rels_xml = '''<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>'''
    rels_path.write_text(rels_xml, encoding="utf-8")
    print("Wrote rels")

# ── ensure presentation.xml.rels has the entry ───────────────────────────────
pres_rels_path = UNPACKED / "ppt" / "_rels" / "presentation.xml.rels"
pres_rels = pres_rels_path.read_text(encoding="utf-8")
if NEW_RID not in pres_rels:
    new_rel = (f'  <Relationship Id="{NEW_RID}" '
               f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
               f'Target="slides/slide{NEW_SLIDE_NUM}.xml"/>\n')
    pres_rels = pres_rels.replace("</Relationships>", new_rel + "</Relationships>")
    pres_rels_path.write_text(pres_rels, encoding="utf-8")
    print("Updated presentation.xml.rels")

# ── ensure presentation.xml has the sldId entry ──────────────────────────────
pres_xml_path = UNPACKED / "ppt" / "presentation.xml"
pres_xml = pres_xml_path.read_text(encoding="utf-8")
if NEW_SLIDE_ID not in pres_xml:
    new_sld_id = f'<p:sldId id="{NEW_SLIDE_ID}" r:id="{NEW_RID}"/>'
    pres_xml = pres_xml.replace(
        '<p:sldId id="256" r:id="rId2"/>',
        f'<p:sldId id="256" r:id="rId2"/>\n    {new_sld_id}'
    )
    pres_xml_path.write_text(pres_xml, encoding="utf-8")
    print("Updated presentation.xml")

# ── pack ──────────────────────────────────────────────────────────────────────
with zipfile.ZipFile(PPTX_OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in sorted(UNPACKED.rglob('*')):
        if f.is_file():
            zf.write(f, f.relative_to(UNPACKED))
print(f"Packed -> {PPTX_OUT}")
