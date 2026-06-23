# E1 paper-integration staging (fill after the sweep; gate-contingent)

Post-sweep, run `scripts/part3_e1_decomp.py`, read `reports/_e1_decomp.md`, then make the mechanical edits below.
The gate (per-defect, capable models): **naming = C0_named − C0** vs **pairing = AFC_bal − C0_named** on G1/S6.

## 1. Figure include (gate-agnostic) — add in §5.1 after the C3/G7 figure
```latex
\begin{figure}[t]
\centering
\includegraphics[width=0.78\linewidth]{figs/fig7_elicitation_decomp.png}
\caption{\textbf{Decomposing the elicitation recovery.} Holding model+image fixed on the freeform set, the
0.50$\to$1.00 jump factors into a \emph{naming} component (C0\_named$-$C0: a single slide, the defect named,
no reference) and a \emph{pairing} component (AFC$-$C0\_named: a clean reference supplied). The AFC\_clean
guess-floor (forced choice over two clean slides) is discounted from the 2-AFC accuracy. <ONE SENTENCE STATING
WHICH COMPONENT DOMINATES per the gate>.}
\label{fig:decomp}
\end{figure}
```

## 2. §5.1 paragraph — pick ONE branch by the gate result

### Branch A — naming ≥ pairing (gate SUPPORTED; title/framing UNCHANGED)
> \paragraph{The recovery is naming, not a paired reference.} A reviewer asks whether the 2-AFC recovery is
> elicitation or merely an easier task (a clean reference handed to the model). We separate them on the same
> freeform items (Fig.~\ref{fig:decomp}): simply \emph{naming} the candidate defect on a single slide
> (C0\_named, no reference) already recovers <NAMING>/<GAP> of the gap (G1 $X\to Y$, S6 $\dots$), while adding a
> paired clean reference (true 2-AFC) contributes the smaller remainder; the clean-vs-clean guess-floor
> (AFC\_clean consistent-invention $=Z$) is near zero, so the forced choice is not picking a winner at random.
> Format suppression—not a missing reference—is the mechanism, and ``not the eyes'' stands.

### Branch B — pairing dominates (gate WEAKENS; soften title + Limitations)
> \paragraph{The recovery is largely a paired reference.} Separating naming from pairing on the same items
> (Fig.~\ref{fig:decomp}), naming alone (C0\_named) recovers only <NAMING> while the paired clean reference
> carries <PAIRING> of the gap. We therefore scope the claim to \emph{relative/paired} elicitation: an
> availability-of-reference effect on G1/S6, not a pure format-suppression of an already-perceived signal.
> <RETITLE: soften "not the eyes" to the format-suppressed subset where C0\_named recovers.>

## 3. Fig 2 caption (line ~297) — turn the confound into a resolved/confirmed point
Append: ``A decomposition (Fig.~\ref{fig:decomp}) attributes this jump to <naming / a paired reference>;''

## 4. Limitations 2-AFC caveat — becomes RESOLVED (Branch A) or CONFIRMED (Branch B)
Find the existing "2-AFC confound" sentence; replace the hedge with the gate verdict + the numeric split.

## 5. reports/part3_hybrid.md claims↔evidence table — add the E1 decomposition row.
## 6. Refresh `paper/arxiv_submission.tar.gz` + isolated recompile (rc=0, page count) at the very end.
