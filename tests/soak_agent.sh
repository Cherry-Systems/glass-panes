# vm-shell agent for tests/soak_test.py. Unlike the plain agent it stops when its desktop session
# ends (sign-out), so a leftover agent can never pick up commands meant for the next session.
while xprop -root _NET_SUPPORTING_WM_CHECK >/dev/null 2>&1; do
  c=$(curl -s -m 25 http://10.0.2.2:18765/cmd) || { sleep 2; continue; }
  [ -n "$c" ] || continue
  bash -c "$c" 2>&1 | head -c 400000 | curl -s --data-binary @- http://10.0.2.2:18765/out
done
