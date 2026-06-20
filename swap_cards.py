import xml.etree.ElementTree as ET

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

path = r'C:\Users\Adar\Desktop\robotics assignment\unpacked_parametric\ppt\slides\slide1.xml'
tree = ET.parse(path)
root = tree.getroot()

spTree = root.find('.//p:spTree', NS)

# Teal card shape IDs: 10-15, Red card shape IDs: 22-27
TEAL_IDS = {'10','11','12','13','14','15'}
RED_IDS  = {'22','23','24','25','26','27'}

TEAL_BASE_Y = 1280160
RED_BASE_Y  = 2194560
SHIFT = RED_BASE_Y - TEAL_BASE_Y  # +914400

def shift_shape_y(sp, delta):
    for off in sp.findall('.//a:off', NS):
        y = int(off.get('y'))
        off.set('y', str(y + delta))

for sp in spTree.findall('p:sp', NS):
    sp_id = sp.find('p:nvSpPr/p:cNvPr', NS).get('id')
    if sp_id in TEAL_IDS:
        shift_shape_y(sp, +SHIFT)
    elif sp_id in RED_IDS:
        shift_shape_y(sp, -SHIFT)

tree.write(path, xml_declaration=True, encoding='utf-8')
print("Done — teal and red cards swapped.")
