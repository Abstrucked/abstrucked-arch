# tmux agent icons

The checked-in `tmux-agent-icons.ttf` maps three monochrome logos from
[theSVG collection on Icones](https://icones.js.org/collection/thesvg) to
single-cell private-use glyphs. tmux renders text in its status bar, so a
terminal font is needed to show the actual SVG logos there.

| Agent | Icones source | Character |
| --- | --- | --- |
| Claude Code | [theSVG:claude-code](https://icones.js.org/collection/thesvg?icon=claude-code) | U+F0000 |
| Codex | [theSVG:codex-openai](https://icones.js.org/collection/thesvg?icon=codex-openai) | U+F0001 |
| OpenCode | [theSVG:opencode](https://icones.js.org/collection/thesvg?icon=opencode) | U+F0002 |

`install.sh --only tmux` links the font into `~/.local/share/fonts` and updates
fontconfig. A terminal restart may be needed for newly installed fonts. If
the font is absent, `tmux-agent` uses its previous Nerd Font glyphs. Each
agent's glyph is colored by state: red blocked, yellow working, blue ready,
green idle. To build the TTF from these SVGs, install `fonttools` and
`svgpathtools` in a virtual environment and run
`python3 scripts/build-tmux-agent-font.py`.

Source icons and the generated font are licensed under the included MIT
license from [theSVG](https://github.com/glincker/thesvg).
