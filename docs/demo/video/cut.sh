#!/bin/sh
# Faultline v0.1 demo cut. Inputs in the current directory:
#   demo-terminal.mov   one `make demo`, recorded from before the command was typed
#   demo-browser-a.mov  the same incident on the incident screen; a citation clicked into Grafana
#   demo-browser-b.mov  the live deployment: an incident it opened and investigated by itself
#   demo-browser-c.mov  README's Results table
#   t1.png .. t5.png    title cards (rendered images - Homebrew's ffmpeg has no drawtext)
# T_INJECT: seconds into demo-terminal.mov where "INJECTING THE FAULT" first appears.
set -eu
T_INJECT=${T_INJECT:-13}
S1_END=$((T_INJECT + 10))          # intro, gate, injection - real time
S3_START=$((T_INJECT + 802))       # the final print begins ~815s in - real time from here
S2_LEN=$((S3_START - S1_END))      # the wait: correlation, settle, investigation
SPEED=$(python3 -c "print(round($S2_LEN/80, 2))")   # compress the wait to ~80s (t2.png says 9.9x)

W=1460; H=1656
FIT="scale=$W:$H:force_original_aspect_ratio=decrease,pad=$W:$H:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p"
CARD="overlay=36:36:enable='lt(t\,6)'"

# The terminal recording is opened three times with input-side seeking, so no branch has to buffer
# the whole fourteen minutes while concat drains the one before it.
ffmpeg -hide_banner -loglevel warning -stats -y \
  -to "$S1_END" -i demo-terminal.mov \
  -ss "$S1_END" -to "$S3_START" -i demo-terminal.mov \
  -ss "$S3_START" -i demo-terminal.mov \
  -i demo-browser-a.mov -i demo-browser-b.mov -i demo-browser-c.mov \
  -i t1.png -i t2.png -i t3.png -i t4.png -i t5.png \
  -filter_complex "\
[0:v]setpts=PTS-STARTPTS,$FIT[a1];[a1][6:v]$CARD[s1];\
[1:v]setpts=(PTS-STARTPTS)/$SPEED,$FIT[a2];[a2][7:v]$CARD[s2];\
[2:v]setpts=PTS-STARTPTS,$FIT[s3];\
[3:v]setpts=PTS-STARTPTS,$FIT[a4];[a4][8:v]$CARD[s4];\
[4:v]setpts=PTS-STARTPTS,$FIT[a5];[a5][9:v]$CARD[s5];\
[5:v]setpts=PTS-STARTPTS,$FIT[a6];[a6][10:v]$CARD[s6];\
[s1][s2][s3][s4][s5][s6]concat=n=6:v=1:a=0[v]" \
  -map "[v]" -an -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p -movflags +faststart faultline-demo-v0.1.mp4

echo; ffprobe -v error -show_entries format=duration:stream=width,height -of csv=p=0 faultline-demo-v0.1.mp4
ls -la faultline-demo-v0.1.mp4
