Output docs/demo.gif

Set Shell "zsh"
Set FontSize 15
Set Width 1000
Set Height 620
Set Theme "Dracula"
Set Padding 20
Set PlaybackSpeed 1.0

# Show help
Type "k3s-dev --help"
Sleep 200ms
Enter
Sleep 2.5s

# Clear and show postgres subcommand
Ctrl+L
Type "k3s-dev postgres --help"
Sleep 200ms
Enter
Sleep 2.5s

# Clear and run the demo flow
Ctrl+L
Type "k3s-dev demo"
Sleep 200ms
Enter
Sleep 8s

# Linger on the final status table
Sleep 2s
