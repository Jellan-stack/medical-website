"""
Kokopyahin ang tunay na LOGO_L / LOGO_M / LOGO_R mula sa LUMA mong app.py
papunta sa BAGONG app.py.

Gamit:   python inject_logos.py app_luma.py app.py
"""
import re
import sys

if len(sys.argv) != 3:
    sys.exit("Gamit: python inject_logos.py <luma_app.py> <bagong_app.py>")

old_path, new_path = sys.argv[1], sys.argv[2]
old = open(old_path, encoding="utf-8").read()
new = open(new_path, encoding="utf-8").read()

for name in ("LOGO_L", "LOGO_M", "LOGO_R"):
    m = re.search(rf"^{name} = '(data:image/[^']+)'\s*$", old, re.M)
    if not m:
        sys.exit(f"Hindi nahanap ang {name} sa {old_path}.")
    new, n = re.subn(rf"^{name} = '[^']*'\s*$", lambda _m: f"{name} = '{m.group(1)}'", new, count=1, flags=re.M)
    if n != 1:
        sys.exit(f"Hindi nahanap ang {name} sa {new_path}.")
    print(f"{name}: nakopya ({len(m.group(1))} chars)")

open(new_path, "w", encoding="utf-8").write(new)
print("Tapos na! Pwede nang patakbuhin ang bagong app.py")
