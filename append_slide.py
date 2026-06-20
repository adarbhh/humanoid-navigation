import copy, zipfile, shutil, os
from lxml import etree

SRC = r"C:\Users\Adar\Desktop\robotics assignment\parametric_study_summary.pptx"
DST = r"C:\Users\Adar\Desktop\robotics assignment\parametric_study.pptx"

def read_zip(path):
    z = zipfile.ZipFile(path, 'r')
    files = {name: z.read(name) for name in z.namelist()}
    z.close()
    return files

def write_zip(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)

src_files = read_zip(SRC)
dst_files = read_zip(DST)

# Find how many slides dst already has
import re
dst_slide_names = sorted([k for k in dst_files if re.match(r'ppt/slides/slide\d+\.xml$', k)])
next_idx = len(dst_slide_names) + 1

# Copy slide XML
src_slide_xml = src_files['ppt/slides/slide1.xml']
new_slide_name = f'ppt/slides/slide{next_idx}.xml'
dst_files[new_slide_name] = src_slide_xml

# Copy slide rels (if any)
src_rels_key = 'ppt/slides/_rels/slide1.xml.rels'
new_rels_name = f'ppt/slides/_rels/slide{next_idx}.xml.rels'
if src_rels_key in src_files:
    dst_files[new_rels_name] = src_files[src_rels_key]
else:
    dst_files[new_rels_name] = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'

# Register slide in presentation.xml
prs_xml = etree.fromstring(dst_files['ppt/presentation.xml'])
NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
sldIdLst = prs_xml.find('.//p:sldIdLst', NS)
existing_ids = [int(el.get('id')) for el in sldIdLst]
new_id = max(existing_ids) + 1

# Get the rId for the new slide from presentation rels
prs_rels_xml = etree.fromstring(dst_files['ppt/_rels/presentation.xml.rels'])
RELS_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
existing_rids = [el.get('Id') for el in prs_rels_xml]
nums = []
for r in existing_rids:
    if r and r.startswith('rId'):
        try: nums.append(int(r[3:]))
        except ValueError: pass
new_rid_num = max(nums) + 1
new_rid = f'rId{new_rid_num}'

# Add to presentation rels
etree.SubElement(prs_rels_xml, 'Relationship', {
    'Id': new_rid,
    'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide',
    'Target': f'slides/slide{next_idx}.xml'
})
dst_files['ppt/_rels/presentation.xml.rels'] = etree.tostring(prs_rels_xml, xml_declaration=True, encoding='UTF-8', standalone=True)

# Add slide to sldIdLst
etree.SubElement(sldIdLst, '{http://schemas.openxmlformats.org/presentationml/2006/main}sldId', {
    'id': str(new_id),
    '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id': new_rid
})
dst_files['ppt/presentation.xml'] = etree.tostring(prs_xml, xml_declaration=True, encoding='UTF-8', standalone=True)

# Update [Content_Types].xml
ct_xml = etree.fromstring(dst_files['[Content_Types].xml'])
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'
etree.SubElement(ct_xml, 'Override', {
    'PartName': f'/ppt/slides/slide{next_idx}.xml',
    'ContentType': 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
})
dst_files['[Content_Types].xml'] = etree.tostring(ct_xml, xml_declaration=True, encoding='UTF-8', standalone=True)

shutil.copy(DST, DST + '.bak2')
write_zip(DST, dst_files)
print(f"Done. Slide added as slide{next_idx} in parametric_study.pptx")
