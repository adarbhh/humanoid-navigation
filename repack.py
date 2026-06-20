import zipfile
from pathlib import Path

UNPACKED = Path("unpacked_pptx")
OUT = Path("robotics_ops_presentation.pptx")

def sort_key(p):
    name = p.relative_to(UNPACKED).as_posix()
    if name == "[Content_Types].xml":
        return (0, name)
    if name == "_rels/.rels":
        return (1, name)
    return (2, name)

files = [f for f in UNPACKED.rglob("*") if f.is_file()]
files.sort(key=sort_key)

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        arcname = f.relative_to(UNPACKED).as_posix()
        zf.write(f, arcname)

print("Done:", OUT)
