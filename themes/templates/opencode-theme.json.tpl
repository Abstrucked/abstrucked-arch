{
  "$schema": "https://opencode.ai/theme.json",
  "base": {
    "categorical": ["accent", "red", "green", "blue", "purple"],
    "text": {
      "base": "{{opencode.base.text.base}}",
      "muted": "{{opencode.base.text.muted}}",
      "action": {
        "primary": {
          "base": "{{opencode.base.text.action.primary.base}}",
          "$hovered": "{{opencode.base.text.action.primary.hovered}}",
          "$focused": "{{opencode.base.text.action.primary.focused}}",
          "$pressed": "{{opencode.base.text.action.primary.pressed}}",
          "$selected": "{{opencode.base.text.action.primary.selected}}",
          "$disabled": "{{opencode.base.text.action.primary.disabled}}"
        },
        "secondary": {
          "base": "{{opencode.base.text.action.secondary.base}}",
          "$hovered": "{{opencode.base.text.action.secondary.hovered}}",
          "$focused": "{{opencode.base.text.action.secondary.focused}}",
          "$pressed": "{{opencode.base.text.action.secondary.pressed}}",
          "$selected": "{{opencode.base.text.action.secondary.selected}}",
          "$disabled": "{{opencode.base.text.action.secondary.disabled}}"
        },
        "destructive": {
          "base": "{{opencode.base.text.action.destructive.base}}",
          "$hovered": "{{opencode.base.text.action.destructive.hovered}}",
          "$focused": "{{opencode.base.text.action.destructive.focused}}",
          "$pressed": "{{opencode.base.text.action.destructive.pressed}}",
          "$selected": "{{opencode.base.text.action.destructive.selected}}",
          "$disabled": "{{opencode.base.text.action.destructive.disabled}}"
        }
      },
      "formfield": {
        "base": "{{opencode.base.text.formfield.base}}",
        "$hovered": "{{opencode.base.text.formfield.hovered}}",
        "$focused": "{{opencode.base.text.formfield.focused}}",
        "$pressed": "{{opencode.base.text.formfield.pressed}}",
        "$selected": "{{opencode.base.text.formfield.selected}}",
        "$disabled": "{{opencode.base.text.formfield.disabled}}"
      },
      "feedback": {
        "error": {"base": "{{opencode.base.text.feedback.error.base}}", "muted": "{{opencode.base.text.feedback.error.muted}}"},
        "warning": {"base": "{{opencode.base.text.feedback.warning.base}}", "muted": "{{opencode.base.text.feedback.warning.muted}}"},
        "success": {"base": "{{opencode.base.text.feedback.success.base}}", "muted": "{{opencode.base.text.feedback.success.muted}}"},
        "info": {"base": "{{opencode.base.text.feedback.info.base}}", "muted": "{{opencode.base.text.feedback.info.muted}}"}
      }
    },
    "background": {
      "base": "{{opencode.base.background.base}}",
      "raised": {
        "base": "{{opencode.base.background.raised.base}}",
        "high": "{{opencode.base.background.raised.high}}",
        "max": "{{opencode.base.background.raised.max}}"
      },
      "action": {
        "primary": {
          "base": "{{opencode.base.background.action.primary.base}}",
          "$hovered": "{{opencode.base.background.action.primary.hovered}}",
          "$focused": "{{opencode.base.background.action.primary.focused}}",
          "$pressed": "{{opencode.base.background.action.primary.pressed}}",
          "$selected": "{{opencode.base.background.action.primary.selected}}",
          "$disabled": "{{opencode.base.background.action.primary.disabled}}"
        },
        "secondary": {
          "base": "{{opencode.base.background.action.secondary.base}}",
          "$hovered": "{{opencode.base.background.action.secondary.hovered}}",
          "$focused": "{{opencode.base.background.action.secondary.focused}}",
          "$pressed": "{{opencode.base.background.action.secondary.pressed}}",
          "$selected": "{{opencode.base.background.action.secondary.selected}}",
          "$disabled": "{{opencode.base.background.action.secondary.disabled}}"
        },
        "destructive": {
          "base": "{{opencode.base.background.action.destructive.base}}",
          "$hovered": "{{opencode.base.background.action.destructive.hovered}}",
          "$focused": "{{opencode.base.background.action.destructive.focused}}",
          "$pressed": "{{opencode.base.background.action.destructive.pressed}}",
          "$selected": "{{opencode.base.background.action.destructive.selected}}",
          "$disabled": "{{opencode.base.background.action.destructive.disabled}}"
        }
      },
      "formfield": {
        "base": "{{opencode.base.background.formfield.base}}",
        "$hovered": "{{opencode.base.background.formfield.hovered}}",
        "$focused": "{{opencode.base.background.formfield.focused}}",
        "$pressed": "{{opencode.base.background.formfield.pressed}}",
        "$selected": "{{opencode.base.background.formfield.selected}}",
        "$disabled": "{{opencode.base.background.formfield.disabled}}"
      },
      "feedback": {
        "error": {"base": "{{opencode.base.background.feedback.error.base}}"},
        "warning": {"base": "{{opencode.base.background.feedback.warning.base}}"},
        "success": {"base": "{{opencode.base.background.feedback.success.base}}"},
        "info": {"base": "{{opencode.base.background.feedback.info.base}}"}
      }
    },
    "border": {"base": "{{opencode.base.border.base}}"},
    "scrollbar": {"base": "{{opencode.base.scrollbar.base}}"},
    "diff": {
      "text": {
        "added": "{{opencode.base.diff.text.added}}",
        "removed": "{{opencode.base.diff.text.removed}}",
        "context": "{{opencode.base.diff.text.context}}",
        "hunkHeader": "{{opencode.base.diff.text.hunkHeader}}"
      },
      "background": {
        "added": "{{opencode.base.diff.background.added}}",
        "removed": "{{opencode.base.diff.background.removed}}",
        "context": "{{opencode.base.diff.background.context}}"
      },
      "highlight": {
        "added": "{{opencode.base.diff.highlight.added}}",
        "removed": "{{opencode.base.diff.highlight.removed}}"
      },
      "lineNumber": {
        "text": "{{opencode.base.diff.lineNumber.text}}",
        "background": {
          "added": "{{opencode.base.diff.lineNumber.background.added}}",
          "removed": "{{opencode.base.diff.lineNumber.background.removed}}"
        }
      }
    },
    "syntax": {
      "comment": "{{opencode.base.syntax.comment}}",
      "keyword": "{{opencode.base.syntax.keyword}}",
      "function": "{{opencode.base.syntax.func}}",
      "variable": "{{opencode.base.syntax.variable}}",
      "string": "{{opencode.base.syntax.string}}",
      "number": "{{opencode.base.syntax.number}}",
      "type": "{{opencode.base.syntax.type}}",
      "operator": "{{opencode.base.syntax.operator}}",
      "punctuation": "{{opencode.base.syntax.punctuation}}"
    },
    "markdown": {
      "text": "{{opencode.base.markdown.text}}",
      "heading": "{{opencode.base.markdown.heading}}",
      "link": "{{opencode.base.markdown.link}}",
      "linkText": "{{opencode.base.markdown.linkText}}",
      "code": "{{opencode.base.markdown.code}}",
      "blockQuote": "{{opencode.base.markdown.blockQuote}}",
      "emphasis": "{{opencode.base.markdown.emphasis}}",
      "strong": "{{opencode.base.markdown.strong}}",
      "horizontalRule": "{{opencode.base.markdown.horizontalRule}}",
      "listItem": "{{opencode.base.markdown.listItem}}",
      "listEnumeration": "{{opencode.base.markdown.listEnumeration}}",
      "image": "{{opencode.base.markdown.image}}",
      "imageText": "{{opencode.base.markdown.imageText}}",
      "codeBlock": "{{opencode.base.markdown.codeBlock}}"
    }
  },
  "{{opencode.variant}}": {
    "hue": {
      "gray": {
        "100": "{{opencode.mode.hue.gray.100}}", "200": "{{opencode.mode.hue.gray.200}}", "300": "{{opencode.mode.hue.gray.300}}",
        "400": "{{opencode.mode.hue.gray.400}}", "500": "{{opencode.mode.hue.gray.500}}", "600": "{{opencode.mode.hue.gray.600}}",
        "700": "{{opencode.mode.hue.gray.700}}", "800": "{{opencode.mode.hue.gray.800}}", "900": "{{opencode.mode.hue.gray.900}}"
      },
      "red": {
        "100": "{{opencode.mode.hue.red.100}}", "200": "{{opencode.mode.hue.red.200}}", "300": "{{opencode.mode.hue.red.300}}",
        "400": "{{opencode.mode.hue.red.400}}", "500": "{{opencode.mode.hue.red.500}}", "600": "{{opencode.mode.hue.red.600}}",
        "700": "{{opencode.mode.hue.red.700}}", "800": "{{opencode.mode.hue.red.800}}", "900": "{{opencode.mode.hue.red.900}}"
      },
      "orange": {
        "100": "{{opencode.mode.hue.orange.100}}", "200": "{{opencode.mode.hue.orange.200}}", "300": "{{opencode.mode.hue.orange.300}}",
        "400": "{{opencode.mode.hue.orange.400}}", "500": "{{opencode.mode.hue.orange.500}}", "600": "{{opencode.mode.hue.orange.600}}",
        "700": "{{opencode.mode.hue.orange.700}}", "800": "{{opencode.mode.hue.orange.800}}", "900": "{{opencode.mode.hue.orange.900}}"
      },
      "yellow": {
        "100": "{{opencode.mode.hue.yellow.100}}", "200": "{{opencode.mode.hue.yellow.200}}", "300": "{{opencode.mode.hue.yellow.300}}",
        "400": "{{opencode.mode.hue.yellow.400}}", "500": "{{opencode.mode.hue.yellow.500}}", "600": "{{opencode.mode.hue.yellow.600}}",
        "700": "{{opencode.mode.hue.yellow.700}}", "800": "{{opencode.mode.hue.yellow.800}}", "900": "{{opencode.mode.hue.yellow.900}}"
      },
      "green": {
        "100": "{{opencode.mode.hue.green.100}}", "200": "{{opencode.mode.hue.green.200}}", "300": "{{opencode.mode.hue.green.300}}",
        "400": "{{opencode.mode.hue.green.400}}", "500": "{{opencode.mode.hue.green.500}}", "600": "{{opencode.mode.hue.green.600}}",
        "700": "{{opencode.mode.hue.green.700}}", "800": "{{opencode.mode.hue.green.800}}", "900": "{{opencode.mode.hue.green.900}}"
      },
      "cyan": {
        "100": "{{opencode.mode.hue.cyan.100}}", "200": "{{opencode.mode.hue.cyan.200}}", "300": "{{opencode.mode.hue.cyan.300}}",
        "400": "{{opencode.mode.hue.cyan.400}}", "500": "{{opencode.mode.hue.cyan.500}}", "600": "{{opencode.mode.hue.cyan.600}}",
        "700": "{{opencode.mode.hue.cyan.700}}", "800": "{{opencode.mode.hue.cyan.800}}", "900": "{{opencode.mode.hue.cyan.900}}"
      },
      "blue": {
        "100": "{{opencode.mode.hue.blue.100}}", "200": "{{opencode.mode.hue.blue.200}}", "300": "{{opencode.mode.hue.blue.300}}",
        "400": "{{opencode.mode.hue.blue.400}}", "500": "{{opencode.mode.hue.blue.500}}", "600": "{{opencode.mode.hue.blue.600}}",
        "700": "{{opencode.mode.hue.blue.700}}", "800": "{{opencode.mode.hue.blue.800}}", "900": "{{opencode.mode.hue.blue.900}}"
      },
      "purple": {
        "100": "{{opencode.mode.hue.purple.100}}", "200": "{{opencode.mode.hue.purple.200}}", "300": "{{opencode.mode.hue.purple.300}}",
        "400": "{{opencode.mode.hue.purple.400}}", "500": "{{opencode.mode.hue.purple.500}}", "600": "{{opencode.mode.hue.purple.600}}",
        "700": "{{opencode.mode.hue.purple.700}}", "800": "{{opencode.mode.hue.purple.800}}", "900": "{{opencode.mode.hue.purple.900}}"
      },
      "accent": "{{opencode.mode.hue.accent}}",
      "interactive": "{{opencode.mode.hue.interactive}}",
      "neutral": "{{opencode.mode.hue.neutral}}"
    },
    "categorical": ["accent", "red", "green", "blue", "purple"]
  }
}
