#!/bin/sh
# Faultline's full cut (T7.5): the plan's beats on the v2 world. Inputs in the current directory:
#   demo-terminal.mov   one `make demo` with FAULTLINE_TOOLS_WORLD=v2, recorded from before the
#                       command was typed, to its last line
#   demo-browser-a.mov  the same incident on the incident screen; a trace citation clicked into
#                       Grafana Explore (Tempo) - the encore
#   demo-approval.mov   the same fault injected again by hand, the recorded proposal approved
#                       (faultline-approve --from-run) and executed (faultline-execute run), and
#                       Grafana's alert list clearing - the approved rollback and recovery, $0
#   demo-browser-c.mov  evals/dashboard/index.html, scrolled
#   t1.png .. t5.png    title cards (python3 cards.py renders them)
# T_INJECT: seconds into demo-terminal.mov where "INJECTING THE FAULT" first appears.
# T_FINAL:  seconds into demo-terminal.mov where "THE INVESTIGATION IS DONE" first appears; the
#           wait between the two is compressed to about 80 s, as the v0.1 cut did.
set -eu
T_INJECT=${T_INJECT:-13}
T_FINAL=${T_FINAL:-420}
S1_END=$((T_INJECT + 10))
S2_LEN=$((T_FINAL - S1_END))
SPEED=$(python3 -c "print(round($S2_LEN/80, 2))")

W=1460; H=1656
FIT="scale=$W:$H:force_original_aspect_ratio=decrease,pad=$W:$H:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p"
CARD="overlay=36:36:enable='lt(t\,6)'"

ffmpeg -hide_banner -loglevel warning -stats -y \
  -to "$S1_END" -i demo-terminal.mov \
  -ss "$S1_END" -to "$T_FINAL" -i demo-terminal.mov \
  -ss "$T_FINAL" -i demo-terminal.mov \
  -i demo-browser-a.mov -i demo-approval.mov -i demo-browser-c.mov \
  -i t1.png -i t2.png -i t3.png -i t4.png -i t5.png \
  -filter_complex "\
[0:v]setpts=PTS-STARTPTS,$FIT[a1];[a1][6:v]$CARD[s1];\
[1:v]setpts=(PTS-STARTPTS)/$SPEED,$FIT[a2];[a2][7:v]$CARD[s2];\
[2:v]setpts=PTS-STARTPTS,$FIT[s3];\
[3:v]setpts=PTS-STARTPTS,$FIT[a4];[a4][8:v]$CARD[s4];\
[4:v]setpts=PTS-STARTPTS,$FIT[a5];[a5][9:v]$CARD[s5];\
[5:v]setpts=PTS-STARTPTS,$FIT[a6];[a6][10:v]$CARD[s6];\
[s1][s2][s3][s4][s5][s6]concat=n=6:v=1:a=0[v]" \
  -map "[v]" -an -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p -movflags +faststart faultline-demo-v0.2.mp4

echo; ffprobe -v error -show_entries format=duration:stream=width,height -of csv=p=0 faultline-demo-v0.2.mp4
ls -la faultline-demo-v0.2.mp4
