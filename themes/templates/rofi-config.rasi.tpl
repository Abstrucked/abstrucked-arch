configuration {
    modi: "combi,drun,run,window";
    show-icons: true;
    font: "JetBrains Mono Nerd Font 11";
    display-drun: "Apps";
    display-run: "Run";
    display-combi: "Search";
    display-window: "Windows";
    matching: "fuzzy";
    drun-display-format: "{name}";
    terminal: "alacritty";
}

* {
    background: {{bg}};
    foreground: {{fg}};
    lightbg: {{surface}};
    selected-normal-background: {{accent}};
    selected-normal-foreground: {{bg}};
    selected-active-background: {{accent}};
    selected-active-foreground: {{bg}};
    active-background: {{surface}};
    active-foreground: {{fg}};
    alternate-normal-background: {{surface}};
    alternate-active-background: {{surface}};
    alternate-active-foreground: {{fg}};
    urgent-background: {{surface}};
    urgent-foreground: {{red}};
    border-color: {{surface_alt}};
}

window {
    width: 45%;
    border: 2px;
    border-radius: 8px;
    padding: 12px;
}

element {
    padding: 6px;
}

element selected {
    background-color: @selected-normal-background;
}
