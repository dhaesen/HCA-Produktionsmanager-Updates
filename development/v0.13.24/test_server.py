from pathlib import Path
from patch_server import patch_text

root=Path(__file__).resolve().parents[2]
source=(root.parent/'build'/'nas-v01322-test.py')
if source.exists():
    text=source.read_text(encoding='utf-8')
else:
    import zipfile
    with zipfile.ZipFile(root.parent/'build'/'HCA_NAS_Erweiterung_v0.13.22.zip') as z:
        text=z.read('app/hca_shared.py').decode('utf-8')
patched=patch_text(text)
assert 'Die Auftragsadresse muss nicht nur an den alten Produktionsserver' in patched
assert '_upsert_meta(base_id' in patched
assert '"shipping_mode": "standard"' in patched
assert patch_text(patched)==patched
compile(patched,'hca_shared.py','exec')
print('v0.13.24 server patch test passed')

