"$schema" = 'https://starship.rs/config-schema.json'

format = """
[░▒▓]({{starship.cap}})\
$os\
[](bg:{{starship.seg1}} fg:{{starship.cap}})\
$directory\
[](fg:{{starship.seg1}} bg:{{starship.seg2}})\
$git_branch\
$git_status\
[](fg:{{starship.seg2}} bg:{{starship.seg3}})\
$nodejs\
$bun\
$rust\
$golang\
$php\
[](fg:{{starship.seg3}} bg:{{starship.seg4}})\
$time\
[ ](fg:{{starship.seg4}})\
\n$character"""

[directory]
style = "fg:{{starship.on_seg1}} bg:{{starship.seg1}}"
format = "[ $path ]($style)"
truncation_length = 3
truncation_symbol = "…/"

[directory.substitutions]
"Documents" = "󰈙 "
"Downloads" = " "
"Music" = " "
"Pictures" = " "

[git_branch]
symbol = ""
style = "bg:{{starship.seg2}}"
format = '[[ $symbol $branch ](fg:{{starship.seg1}} bg:{{starship.seg2}})]($style)'

[git_status]
style = "bg:{{starship.seg2}}"
format = '[[($all_status$ahead_behind )](fg:{{starship.seg1}} bg:{{starship.seg2}})]($style)'

[nodejs]
symbol = ""
style = "bg:{{starship.seg3}}"
format = '[[ $symbol ($version) ](fg:{{starship.seg1}} bg:{{starship.seg3}})]($style)'

[bun]
symbol = ""
style = "bg:{{starship.seg3}}"
format = '[[ $symbol ($version) ](fg:{{starship.seg1}} bg:{{starship.seg3}})]($style)'

[rust]
symbol = ""
style = "bg:{{starship.seg3}}"
format = '[[ $symbol ($version) ](fg:{{starship.seg1}} bg:{{starship.seg3}})]($style)'

[golang]
symbol = ""
style = "bg:{{starship.seg3}}"
format = '[[ $symbol ($version) ](fg:{{starship.seg1}} bg:{{starship.seg3}})]($style)'

[php]
symbol = ""
style = "bg:{{starship.seg3}}"
format = '[[ $symbol ($version) ](fg:{{starship.seg1}} bg:{{starship.seg3}})]($style)'

[time]
disabled = false
time_format = "%R" # Hour:Minute Format
style = "bg:{{starship.seg4}}"
format = '[[  $time ](fg:{{starship.text}} bg:{{starship.seg4}})]($style)'

[os]
style = "bg:{{starship.cap}} fg:{{starship.on_cap}}"
format = "[ $symbol ]($style)"
disabled = false

[os.symbols]
Windows = "󰍲"
Ubuntu = "󰕈"
SUSE = ""
Raspbian = "󰐿"
Mint = "󰣭"
Macos = "󰀵"
Manjaro = ""
Linux = "󰌽"
Gentoo = "󰣨"
Fedora = "󰣛"
Alpine = ""
Amazon = ""
Android = ""
AOSC = ""
Arch = "󰣇"
Artix = "󰣇"
EndeavourOS = ""
CentOS = ""
Debian = "󰣚"
Redhat = "󱄛"
RedHatEnterprise = "󱄛"
Pop = ""
