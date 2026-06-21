#!/bin/bash
# Protocol-2 eval sharded across TWO Qwen3.5-27B servers (GPU0,1 @8101 + GPU2,3 @8102)
# to use all four cards. Each server runs a synth shard then a slideaudit shard;
# results are merged at the end. (G1 is linter-routed now, so no slow C2 stage.)
set -u
cd /home/gpus/slide-examiner
PY=/home/gpus/anaconda3/envs/slide-examiner/bin/python
export PART3_CHAT_KWARGS='{"chat_template_kwargs":{"enable_thinking":false}}'
D=data/part3
L=runs/part3/p2
MT=512

# ---- server 1 (8101, GPU0,1, max_num_seqs=6): synth half + slideaudit half ----
( $PY scripts/part3_p2_eval.py --base-url http://127.0.0.1:8101/v1 --model qwen35-27b \
      --style scoped --max-per-defect 40 --workers 6 --max-tokens $MT \
      --classes G2_ELEMENT_OVERLAP G3_ALIGNMENT_OFFSET G5_BRAND_COLOR_VIOLATION G6_MARGIN_VIOLATION S6_IMAGE_TEXT_CONTRADICTION \
      --out $D/p2_synth_s1.json \
  && $PY scripts/part3_p2_slideaudit.py --base-url http://127.0.0.1:8101/v1 --model qwen35-27b \
      --style scoped --max-per-defect 40 --workers 6 --max-tokens $MT \
      --classes G1_TEXT_OVERFLOW G2_ELEMENT_OVERLAP G3_ALIGNMENT_OFFSET G4_FONT_SIZE_INCONSISTENCY \
      --out $D/p2_sa_s1.json ) > $L/shard_s1.log 2>&1 &
P1=$!

# ---- server 2 (8102, GPU2,3, max_num_seqs=8): synth half + slideaudit half ----
( $PY scripts/part3_p2_eval.py --base-url http://127.0.0.1:8102/v1 --model qwen35-27b \
      --style scoped --max-per-defect 40 --workers 8 --max-tokens $MT \
      --classes G1_TEXT_OVERFLOW G7_RENDER_CONTAINMENT_OVERFLOW S1_TITLE_BODY_MISMATCH S4_DENSITY_RULE_VIOLATION \
      --out $D/p2_synth_s2.json \
  && $PY scripts/part3_p2_slideaudit.py --base-url http://127.0.0.1:8102/v1 --model qwen35-27b \
      --style scoped --max-per-defect 40 --workers 8 --max-tokens $MT \
      --classes G5_BRAND_COLOR_VIOLATION G6_MARGIN_VIOLATION S4_DENSITY_RULE_VIOLATION \
      --out $D/p2_sa_s2.json ) > $L/shard_s2.log 2>&1 &
P2=$!

wait $P1; R1=$?
wait $P2; R2=$?
echo "shard1 rc=$R1 shard2 rc=$R2"

# ---- merge ----
$PY scripts/part3_p2_merge.py synth $D/p2_synth.json $D/p2_synth_s1.json $D/p2_synth_s2.json
$PY scripts/part3_p2_merge.py sa    $D/p2_slideaudit.json $D/p2_sa_s1.json $D/p2_sa_s2.json
echo "PARALLEL-EVAL-DONE"
