Output docs/walkthrough.gif

Set Shell "zsh"
Set FontSize 14
Set Width 1100
Set Height 750
Set Theme "Dracula"
Set Padding 20
Set PlaybackSpeed 1.0

# Starting state
Type "k3s-dev-env status"
Sleep 200ms
Enter
Sleep 5s

Ctrl+L

# Step 1: install the Sealed Secrets controller
Type "k3s-dev-env sealed-secrets install"
Sleep 200ms
Enter
Sleep 15s

Ctrl+L

# Step 2: create a namespace
Type "k3s-dev-env namespace add myapp"
Sleep 200ms
Enter
Sleep 5s

# Step 3: provision Postgres
Type "k3s-dev-env postgres add myapp --namespace myapp --user myapp --db myapp_db"
Sleep 200ms
Enter
Sleep 15s

Ctrl+L

# Full status — cluster, sealed secrets, namespace, postgres
Type "k3s-dev-env status"
Sleep 200ms
Enter
Sleep 6s

Ctrl+L

# Show connection URLs
Type "k3s-dev-env postgres connect myapp"
Sleep 200ms
Enter
Sleep 4s

Ctrl+L

# Teardown — remove postgres (clears keychain + k8s resources)
Type "k3s-dev-env postgres remove myapp --yes"
Sleep 200ms
Enter
Sleep 10s

# Remove namespace
Type "k3s-dev-env namespace remove myapp"
Sleep 200ms
Enter
Sleep 14s

# Final status
Type "k3s-dev-env status"
Sleep 200ms
Enter
Sleep 6s
