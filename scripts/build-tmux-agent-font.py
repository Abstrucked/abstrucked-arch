#!/usr/bin/env python3
"""Build the tmux status glyph font from theSVG's monochrome agent logos.

Regenerate with: pip install fonttools svgpathtools
                 python3 scripts/build-tmux-agent-font.py
The checked-in TTF is used at runtime; the build has no runtime dependencies.
"""

from pathlib import Path
import xml.etree.ElementTree as ET

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from svgpathtools import CubicBezier, Line, Path as SvgPath, QuadraticBezier, parse_path


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "config/tmux/agent-icons"
CODEPOINTS = {"claude": 0xF0000, "codex": 0xF0001, "opencode": 0xF0002}


def scaled(point):
    # A single cell at 1000 units/em, with breathing room at status-bar size.
    return (round(140 + point.real * 30), round(800 - point.imag * 30))


def signed_area(contour):
    # Shoelace on sampled points: sufficient to distinguish the large logo
    # outline from tiny holes without svgpathtools' costly numeric integration.
    points = [segment.point(t / 4) for segment in contour for t in range(4)]
    points.append(points[0])
    return sum(a.real * b.imag - b.real * a.imag for a, b in zip(points, points[1:]))


def glyph_for(name):
    root = ET.parse(ICONS / f"{name}.svg").getroot()
    pen = TTGlyphPen(None)
    curve_pen = Cu2QuPen(pen, max_err=1, reverse_direction=False)
    for element in root.iter():
        if not element.tag.endswith("}path"):
            continue
        contours = parse_path(element.attrib["d"]).continuous_subpaths()
        # SVG evenodd fill draws the small internal contours as holes. TrueType
        # uses nonzero winding, so reverse inner contours when needed.
        outer = max(contours, key=lambda p: abs(signed_area(p)))
        outer_sign = 1 if signed_area(outer) > 0 else -1
        for contour in contours:
            if contour is not outer and signed_area(contour) * outer_sign > 0:
                contour = SvgPath(*(segment.reversed() for segment in reversed(contour)))
            curve_pen.moveTo(scaled(contour.start))
            for segment in contour:
                if isinstance(segment, Line):
                    curve_pen.lineTo(scaled(segment.end))
                elif isinstance(segment, CubicBezier):
                    curve_pen.curveTo(
                        scaled(segment.control1), scaled(segment.control2), scaled(segment.end)
                    )
                elif isinstance(segment, QuadraticBezier):
                    curve_pen.qCurveTo(scaled(segment.control), scaled(segment.end))
                else:
                    for cubic in segment.as_cubic_curves():
                        curve_pen.curveTo(
                            scaled(cubic.control1), scaled(cubic.control2), scaled(cubic.end)
                        )
            curve_pen.closePath()
    return pen.glyph()


def main():
    font = FontBuilder(1000, isTTF=True)
    order = [".notdef", *CODEPOINTS]
    font.setupGlyphOrder(order)
    font.setupCharacterMap({codepoint: name for name, codepoint in CODEPOINTS.items()})
    empty = TTGlyphPen(None).glyph()
    font.setupGlyf({".notdef": empty, **{name: glyph_for(name) for name in CODEPOINTS}})
    font.setupHorizontalMetrics({name: (1000, 0) for name in order})
    font.setupHorizontalHeader(ascent=850, descent=-150)
    font.setupNameTable({
        "familyName": "Tmux Agent Icons",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Tmux Agent Icons 1.0",
        "fullName": "Tmux Agent Icons",
        "psName": "TmuxAgentIcons-Regular",
        "version": "Version 1.0",
    })
    font.setupOS2(sTypoAscender=850, sTypoDescender=-150, usWinAscent=850, usWinDescent=150)
    font.setupPost()
    font.setupMaxp()
    font.save(ICONS / "tmux-agent-icons.ttf")


if __name__ == "__main__":
    main()
