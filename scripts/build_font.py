"""Subset an OFL Noto CJK font to the plugin's finite display vocabulary."""

import argparse
import hashlib
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    text = (
        "".join(chr(x) for x in range(32, 127)) + "闰正冬腊月初十廿卅一二三四五六七八九零〇年月日时"
    )
    for path in ROOT.rglob("*"):
        if any(x.startswith(".") for x in path.relative_to(ROOT).parts):
            continue
        if path.suffix in {".py", ".json", ".md"}:
            text += path.read_text(encoding="utf-8")
    font = TTFont(args.source)
    options = subset.Options()
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17]
    options.name_legacy = True
    options.name_languages = [0x409]
    sub = subset.Subsetter(options=options)
    sub.populate(text=text)
    sub.subset(font)
    for name in font["name"].names:
        if name.nameID in (1, 3, 4, 6, 16):
            name.string = "GanzhiSans".encode(name.getEncoding())
    if "CFF " in font:
        cff = font["CFF "].cff
        cff.fontNames = ["GanzhiSans"]
        cff.topDictIndex[0].FullName = "GanzhiSans"
        cff.topDictIndex[0].FamilyName = "GanzhiSans"
    dest = ROOT / "assets" / "fonts" / "GanzhiSans.otf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    font.save(dest)
    info = {
        "source": "https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "output_bytes": dest.stat().st_size,
        "license": "SIL Open Font License 1.1; see LICENSE.txt",
        "modification": "Subset of display vocabulary, renamed GanzhiSans; original font copyright retained in font metadata.",
    }
    (dest.parent / "provenance.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Font: {dest.stat().st_size} bytes")


if __name__ == "__main__":
    main()
