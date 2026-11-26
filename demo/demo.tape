Output demo/demo.gif

Set Shell bash
Set FontSize 16
Set Width 1280
Set Height 640
Set Padding 20
Set TypingSpeed 40ms
Env BASH_SILENCE_DEPRECATION_WARNING "1"

# Show $HOME as ~ in prco's output; `script` keeps it attached to a tty so
# colors survive the pipe.
Hide
Type `export PS1='$ '; prco() { script -q /dev/null prco "$@" | sed "s|$HOME|~|g"; }; clear`
Enter
Show

Sleep 500ms
Type "prco https://github.com/Tener/prco/pull/1"
Sleep 500ms
Enter
Wait@60s /^\$ ?$/
Sleep 5s

# Remove the worktree so the tape can be re-run.
Hide
Type "~/code/prco-pr-1/WORKTREE_REMOVE.sh"
Enter
Wait@30s /^\$ ?$/
