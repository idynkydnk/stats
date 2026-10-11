"""Subset Font Awesome 5.15.4 from a downloaded upstream directory.

Build-time only: pip install 'fonttools[woff]'. Download all.min.css, the three
WOFF2 fonts, and LICENSE.txt from the official 5.15.4 distribution into one
directory, then run: python scripts/build_site_icons.py SOURCE_DIRECTORY.
Runtime hosting needs no font tools or external icon requests.
"""
from hashlib import sha256
from pathlib import Path
import re
import shutil
import sys

from fontTools import subset
from fontTools.ttLib import TTFont

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1])
destination = root / 'static/vendor/fontawesome'
destination.mkdir(parents=True, exist_ok=True)
files = list((root / 'templates').rglob('*.html')) + list((root / 'static/js').glob('*.js')) + list(root.glob('*.py'))
used = set(re.findall(r'\bfa-[a-z0-9-]+', '\n'.join(path.read_text() for path in files)))
original = (source / 'all.min.css').read_text()
rules = re.findall(r'([^{}]+)\{content:"\\([0-9a-f]+)"\}', original)
selected = [(selectors, code) for selectors, code in rules
            if used.intersection(re.findall(r'fa-[a-z0-9-]+', selectors))]
unicodes = {int(code, 16) for _, code in selected}
css = original[:original.index('.fa-500px:before')]
css += '\n' + '\n'.join(selectors + '{content:"\\' + code + '"}' for selectors, code in selected)
css += original[original.index('.sr-only{'):original.index('@font-face')]
for name, family, weight, classes in [
    ('fa-solid-900', 'Font Awesome 5 Free', 900, '.fa,.fas'),
    ('fa-regular-400', 'Font Awesome 5 Free', 400, '.far'),
    ('fa-brands-400', 'Font Awesome 5 Brands', 400, '.fab'),
]:
    font = TTFont(source / (name + '.woff2'))
    font.recalcTimestamp = False
    options = subset.Options()
    options.recalc_timestamp = False
    worker = subset.Subsetter(options=options)
    worker.populate(unicodes=unicodes)
    worker.subset(font)
    temporary = destination / (name + '.woff2')
    font.save(temporary)
    digest = sha256(temporary.read_bytes()).hexdigest()[:16]
    filename = name + '.' + digest + '.woff2'
    temporary.replace(destination / filename)
    for previous in destination.glob(name + '.*.woff2'):
        if previous.name != filename:
            previous.unlink()
    css += (f'\n@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};'
            f'font-display:block;src:url("{filename}") format("woff2")}}'
            f'\n{classes}{{font-family:"{family}";font-weight:{weight}}}')
(destination / 'icons.css').write_text(css + '\n')
shutil.copyfile(source / 'LICENSE.txt', destination / 'LICENSE.txt')
print(f'Included {len(selected)} icon rules; assets total ' + str(sum(p.stat().st_size for p in destination.glob('*') if p.suffix != '.txt')) + ' bytes')
