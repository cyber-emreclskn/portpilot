# Record the README demo with VHS: https://github.com/charmbracelet/vhs
#   brew install vhs   (or: go install github.com/charmbracelet/vhs@latest)
#   vhs docs/demo.tape
Output docs/demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 640
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms

Hide
Type "python3 -m http.server 8000 >/dev/null 2>&1 & python3 -m http.server 3000 >/dev/null 2>&1 & clear"
Enter
Sleep 1s
Show

Type "pp list"
Enter
Sleep 2s

Type "pp"
Enter
Sleep 2s
Type "/"
Type "3000"
Sleep 1s
Enter
Sleep 500ms
Type "k"
Sleep 1.5s
Type "y"
Sleep 2s
Type "q"
Sleep 500ms

Type "pp kill 8000 -y"
Enter
Sleep 2s
