# Wafer-map defect signatures → equipment cause → trend monitoring (English summary)

> One line: this repository classifies 25,519 real wafer maps (WM-811K) into 8 defect patterns (macro-F1 0.907 ± 0.008 over 5 lot-level splits), links each pattern to the check order, tool-side evidence and hand-off criteria of TEL equipment modules, and puts SPC control charts on top of the classifier output to find when a trend started. It is written from the viewpoint of an equipment vendor's technical support engineer. The Korean [`README.md`](../README.md) is the primary document; this page summarizes it in English. Japanese terminology is in the three-language table [`glossary.md`](glossary.md) (no Japanese prose).

Everything verified on synthetic data is a **logic check, not a performance number**. The only measured numbers are the classifier results on WM-811K.

## 1. Viewpoint

A die-level pass/fail wafer map (effectively a wafer-test bin map) is the accumulated result of every process step. The customer's yield team owns the bin maps, lot history and retest results; the vendor's engineer sees a map only when the customer escalates. What the vendor engineer owns is **tool-side evidence**: alarm/event logs, consumable counters (RF hours, wafer counts), recipe-change history, PM and part-replacement records, robot teaching/centering logs, chamber seasoning history, ESC He pressure and zone temperature logs. So every pattern table separates customer-side from tool-side evidence and ends with a "TEL cause vs hand-off to another vendor's tool" criterion. The single source of all action text is `wafer_pattern_classifier.ACTION_DETAIL`; `tests/test_actions.py` checks that code and documents agree.

TEL product names follow tel.com as of 2026-10: coater/developer CLEAN TRACK LITHIUS Pro series, plasma etch Tactras / Episode UL, gas chemical etch Certas LEAGA, batch furnace TELINDY PLUS, single-wafer deposition Triase+ / Episode / NT333, cleaning CELLESTA / EXPEDIUS / NS300, wafer prober Precio / Prexa, bonder Synapse. TEL does not make CMP, lithography scanners or stand-alone inspection tools, so those items are marked "hand-off". Nothing here assumes TEL internal structures, manuals or PM intervals; unverified items are marked "(estimate)". Sources and their verification level are in [`references.md`](references.md).

## 2. Results (test lots, macro-F1 over the 8 defect classes)

| # | Stage | Features | macro-F1 | Script |
|---|---|---|---|---|
| 0 | Synthetic self-check | — | 7/7 | `wafer_pattern_classifier.py` (coding check, not performance) |
| 1 | Rules, uncalibrated | 6 global | **0.167** | `wm811k_evaluate.py` |
| 2 | Rules, calibrated on train lots | 6 global | 0.558 | `wm811k_calibrate.py` |
| 2′ | Rules, calibrated | 6 global + 11 structural | 0.625 | `wm811k_structural.py` |
| 3 | Decision tree | 6 global | 0.710 | `wm811k_calibrate.py` |
| 3′ | Random forest | 6 global | 0.765 | `wm811k_calibrate.py` |
| 4 | Decision tree | 17 | 0.827 | `wm811k_structural.py` |
| 5 | Random forest | 17 | 0.878 ± 0.008 | `wm811k_validate.py` (5 seeds) |
| 6 | **Random forest** | **20 (global + structural + position)** | **0.907 ± 0.008** | `wm811k_validate.py` (5 seeds, train 0.99) |

Data: 25,519 wafers with one of 8 defect labels, 8,047 lots, 329 map sizes (lot and size counts are computed by this repository, not quoted from the paper). Split: by lot (`lotName` group split; wafers of the same lot share patterns, so a random split leaks). Metric: macro-F1 fixed to the 8 defect classes (EDGE_RING 9,680 vs NEAR_FULL 149 is a 65x imbalance, so accuracy is meaningless; CLEAN, which appears only in predictions, is kept out of the label set). Final numbers are mean ± std over 5 seeds; the single seed-42 split gave 0.890 → 0.919, which is why the repeated validation exists.

Per-class F1 (20 features, mean of 5): CENTER 0.97 · EDGE_RING 0.98 · NEAR_FULL 0.98 · EDGE_LOC 0.91 · RANDOM 0.90 · DONUT 0.86 · LOC 0.84 · SCRATCH 0.83. Remaining errors: LOC → EDGE_LOC (542 wafers summed over 5 runs), SCRATCH → LOC (270). Full experiment log: [`validation_log.md`](validation_log.md); reproduction artifacts: [`../results/`](../results/README.md).

## 3. Diagnostic process (7 steps)

1. **0.167 was not a missing-feature problem.** Single-feature AUCs were already high (EDGE_RING: r_mean 0.956; NEAR_FULL: fail_frac 1.000; CENTER: r_std 0.966). The thresholds had been set on noise-free synthetic data; real maps carry sporadic failures on top of the pattern, which pushes every radial statistic outward.
2. **Calibration on train lots only: +0.373.** `center_r` 0.30 → 0.74, `ring_std` 0.15 → 0.24. The size of the shift is the distance between synthetic and real data. Test lots were used once, at the end.
3. **A random forest on the same 6 features is +0.227 higher.** The tree reaches CENTER through `r_std > 0.27 & axial_c ≤ 0.17` without looking at the radius; ordered if-else rules cannot express such alternative paths. The value of hand-written rules narrows to interpretability.
4. **SCRATCH stays at F1 0.319 even with a tree.** Axial concentration AUC is only 0.682: a thin connected line is not representable by global summary statistics.
5. **11 structural features: RF 0.765 → 0.878.** Each feature was designed for a class and checked by AUC: innermost radial-bin failure rate (prof0) → CENTER 0.990, middle bin (prof2) → DONUT 0.980, largest-component elongation → SCRATCH 0.930, outer angular coverage → EDGE_RING 0.808. SCRATCH F1 0.325 → 0.765. One assumption was wrong: RANDOM was expected to be "dozens of small components", but real maps are dense enough that components are few and large (n_comp AUC 0.155); calibration invalidated that rule and the failure is recorded.
6. **3 position features for the EDGE_LOC↔LOC confusion: 0.878 → 0.907.** Largest-component centroid radius (big_r, AUC 0.846) and innermost radius (big_r_min, 0.807) worked; angular span (big_span, AUC 0.520) did not, because both classes have the same span (54° vs 52°). Improvement in all 5 paired splits, Δ +0.030 = 4x the between-split std of 0.008. SCRATCH also gained +0.083 without being targeted.
7. **RF regularization.** `min_samples_leaf` chosen by inner GroupKFold on train (= 2). Larger leaves shrink the train/test gap 0.074 → 0.014 but test also drops 0.919 → 0.887, so leaf = 2 is kept and both train and test are always reported.

Experiment 8 (`wm811k_improve.py`: 8 noise-robust features + HistGradientBoosting, paired on the same 5 splits) is **not measured on real data** yet; only the synthetic end-to-end run is confirmed.

## 4. When a map comes in (8-step field procedure)

Same as the field procedure in [`defect_signatures.md`](defect_signatures.md). Steps 3–7 are verified on synthetic data only, because WM-811K has no timestamps, chamber, slot or tool history; in the real defect subset most lots have too few wafers (3.2 per lot on average), so the lot-level tools return `insufficient`.

1. **Receive the escalation and classify the map.** Ask for the bin map, lot history (which TEL chamber, when), retest status. Playbook: `python wafer_pattern_classifier.py --actions EDGE_RING`; lot batch report: `python batch_wafer_report.py --anonymize`.
2. **Rule out test causes.** NEAR_FULL and grid-periodic patterns can come from the probe card or test program; a retest is the cheapest check (`--actions NEAR_FULL`, field `rule_out_first`). If the prober is Precio / Prexa, the TEL prober check (card cleaning, touchdown counter) goes alongside.
3. **Does it repeat within the lot?** Whole lot → process condition or tool state; one wafer → handling or particle event: `python wm811k_lot_report.py data/wm811k_defects.pkl --pred test_predictions.csv --lot <lot>` (`--demo`). For batch tools (TELINDY PLUS furnace, EXPEDIUS wet bench) the signature is the pattern rate by boat slot: `python wm811k_slot.py test_predictions.csv --pattern EDGE_RING`.
4. **Notch-relative azimuth / scratch shape.** Same angle across the lot → fixed chamber element (exhaust port, gas inlet); scattered → handling: `python wm811k_azimuth.py --demo`. Straight line (transfer system, common to all TEL tools) vs arc (CMP, hand-off; a rule of thumb, not a law): `python wm811k_scratch_shape.py --demo`. Notch direction is an assumption (`--notch-deg`).
5. **Match tool-side evidence.** Alarm/event logs, consumable counters (edge-ring RF hours, wafers since seasoning), recipe/PM history, robot teaching logs, ESC He pressure and zone temperatures, pulled for the lot's processing time: `ACTION_DETAIL[pattern]["tool_evidence"]`.
6. **Tool commonality.** Which tools/chambers the bad lots shared: `python wm811k_commonality.py test_predictions.csv --history lot_history.csv --pattern EDGE_LOC` (`--demo`; input schema in [`lot_history_schema.md`](lot_history_schema.md)).
7. **Since when?** Pattern-rate control chart with PM / part-replacement events overlaid: `python wm811k_spc.py test_predictions.csv --time-col <t> --event-col <event> --group-col chamber` (`--demo`). If the onset coincides with an event, that is the answer.
8. **TEL cause or hand-off, then report.** Decide with `ACTION_DETAIL[pattern]["handoff"]`, then initial → interim → closing reports ([`handoff.md`](handoff.md)). A fully worked synthetic example in 8D form: [`case_study_8d.md`](case_study_8d.md).

## 5. Pattern → suspected module → checks (summary of `defect_signatures.md`)

Default severity: NEAR_FULL = line-stop review (`line_stop_review`), RANDOM = monitor, all others = lot-hold review (`lot_hold`), one level up if it repeats within the lot.

| Pattern | Mechanism (short) | TEL modules to check first | Hand-off (non-TEL) | First checks | Classifier evidence |
|---|---|---|---|---|---|
| EDGE_RING (full-circumference edge band) | Boundary conditions change at the wafer edge in every rotationally symmetric process: etch sheath bending corrected by the edge (focus) ring, a consumable whose wear distorts the sheath and tilts ions; ESC edge seal-band wear/polymer → He leak → hot edge; CVD heater edge drop; coater EBR width mismatch between layers; batch wet-bench edge concentration | Tactras / Episode UL: edge-ring RF counter, ring-height and edge DC-bias correction values, ESC edge-zone temperature, He pressure, seal band. Triase+ / Episode / NT333: heater edge zone, center/edge gas split. TELINDY PLUS: pattern rate by boat slot, quartz boat/tube. CLEAN TRACK LITHIUS Pro: EBR width per layer. EXPEDIUS: bath/dry edge concentration | CMP retaining-ring wear (edge removal-rate profile shift, either fast or slow edge) | (1) ring-width trend across lots: gradual → consumable wear, sudden → compare with part change / recipe / PM time; (2) etch: ring RF counter and correction limits; (3) ESC edge zone logs; (4) deposition heater edge zone, furnace slot rate; (5) coater EBR per layer; (6) wet bench / CMP hand-off | r_mean AUC 0.956, outer_cover 0.808; F1 0.98 |
| EDGE_LOC (one edge arc) | Broken rotational symmetry: robot placing the wafer off-center, exhaust/gas-inlet asymmetry, coater EBR eccentricity (nozzle position, chuck centering), edge chipping. Notch misalignment only rotates an existing asymmetry (same pattern at different angles per wafer). Lift pins sit at 3 × 120° on one radius, so a single arc is not a pin signature | All TEL tools: EFEM robot centering/teaching, aligner. Etch/deposition chambers: exhaust and gas-inlet asymmetry. CLEAN TRACK LITHIUS Pro: EBR eccentricity (4-direction EBR width) | Transfer systems of other vendors' tools: same angle in lots that never passed a TEL chamber | (1) notch-relative azimuth per chamber (`wm811k_azimuth.py`): same angle → fixed chamber element, scattered → handling; (2) robot centering offsets, aligner notch logs; (3) EBR eccentricity; (4) chamber drawing vs angle; (5) edge chipping, end-effector / FOUP slot marks | r_mean high, dir_c high; big_r / big_r_min separate it from LOC (AUC 0.846 / 0.807), big_span useless (0.520); F1 0.91 |
| CENTER (central disc) | Center condition of a rotationally symmetric process: ESC center-zone temperature/heater, per-zone He pressure ratio (He leaks occur at the edge seal and lift-pin holes, never "at the center"); VHF CCP standing-wave effect gives center-high power (a CENTER cause, not DONUT); showerhead center hole clogging; spin-coat center thickness (nozzle centering, dispense timing); single-wafer clean nozzle dwell | Tactras / Episode UL: ESC center zone, He zone ratio, matcher settings. Triase+ / Episode / NT333: showerhead center, heater center zone. CLEAN TRACK LITHIUS Pro: dispense nozzle centering. CELLESTA: nozzle scan profile | CMP head center-zone pressure | (1) does the disc radius match the ESC/heater center-zone radius (zone control) or not (showerhead/nozzle); (2) ESC center zone, He ratio; (3) VHF matcher / low-frequency mix change history; (4) showerhead clogging, cleaning interval; (5) coater nozzle centering, clean nozzle scan | r_std AUC 0.966, prof0 0.990; F1 0.97 |
| DONUT (mid-radius ring) | An extremum in the radial profile: multi-zone heater/ESC zone boundary, multi-zone CMP head, spin-coat thickness ring, bake-plate zone boundary (estimate), wafer bow losing chuck contact at one radius. Standing wave + skin effect overlap or high pressure is only a secondary cause | Tactras / Episode UL: ESC zone boundary, pressure conditions. Triase+ / Episode: heater zone boundary. TELINDY PLUS: zones run along the boat axis, so look at slot-dependent rates. CLEAN TRACK LITHIUS Pro: spin thickness ring, bake plate (estimate) | CMP multi-zone head boundary | (1) ring radius (r_med) vs tool zone-boundary radius; (2) etch pressure/frequency change history; (3) coater spin/dispense recipe, bake plate; (4) bow correlation; (5) CMP hand-off | prof2 AUC 0.980; F1 0.86 (555 wafers, second rarest) |
| SCRATCH (thin line, straight or arc) | Mechanical contact or liquid trajectory. CMP leaves mostly arcs (wafer and pad both rotate); transfer drag (end-effector, pins, cassette slots) is mostly straight — a rule of thumb. The better discriminator is whether direction and position repeat within the lot relative to the notch (fixed handling contact repeats; CMP particles are random). Coater: radial line clusters toward the center ← low dispense volume; diagonal with swirled ends ← developer nozzle contamination; EBR nozzle solvent drops. Probe cards do not make linear scratches (their signature is grid-periodic) | All TEL tools: EFEM robot, end-effector, FOUP slot. CLEAN TRACK LITHIUS Pro: dispense volume, developer nozzle, EBR nozzle. CELLESTA: nozzle-track arcs/radial lines | CMP slurry filter, pad, conditioner, retaining-ring groove; post-CMP brush | (1) arc vs line (`wm811k_scratch_shape.py`) and notch-relative repetition within the lot; (2) transfer system: end-effector pads, FOUP/cassette slot drag, slip marks, teaching logs; (3) coater: radial → dispense, swirl → developer nozzle, EBR drops; (4) clean nozzle track; (5) arc + only right after CMP → hand-off; (6) grid-periodic → not a scratch, see LOC / NEAR_FULL prober items | axial_c AUC only 0.682; elongation 0.930; F1 0.319 (tree, global) → 0.765 (structural RF, single split) → 0.83 (5-run mean, 20 features) |
| LOC (local cluster away from the edge) | Local event: particle shower from flaking chamber-wall deposits, backside particle (≳150 nm) lifting the wafer into a defocus hot spot, local contamination. Three points at 120° on one radius = lift pins. Repetition at the same in-field coordinate of every exposure shot = reticle repeater; repetition at the same die coordinate within a shot = process margin, not reticle. Probe-card site failures repeat with the touchdown grid | Tactras / Episode UL, Triase+ / Episode, TELINDY PLUS: lift pins, seasoning, particles. CLEAN TRACK LITHIUS Pro: EBR width, edge gripper. Precio / Prexa: multi-site card site if touchdown-grid periodic | Reticle / scanner (shot-pitch repeater); stand-alone inspection tool trends | (1) same location across the lot (fixed element) or not (particle event); (2) 3 × 120° → lift pins, identify the module by radius and angle; (3) shot-pitch → reticle hand-off, die-pitch → process margin; (4) particle shower: wafers since seasoning, particle count after PM (`wm811k_spc.py --event-col`); (5) backside particle inspection of the previous deposition/coating step; (6) coater EBR width, gripper | Hardest class; F1 0.84; confused with EDGE_LOC (542 over 5 runs); big_r 0.846, big_r_min 0.807 |
| RANDOM (no spatial structure) | Baseline defect density of the line: particles, gate-oxide defects, random litho defects. The Poisson yield model presupposes this regime; real fab data cluster, which is already LOC / EDGE_LOC. Cleaning-tool changes (batch ↔ single-wafer) shift the baseline density; Certas LEAGA is liquid-free (no watermarks) | Etch / deposition / furnace chambers: seasoning and particles right after PM. CELLESTA / EXPEDIUS / NS300: baseline defect density. CLEAN TRACK LITHIUS Pro: too-narrow EBR → flakes | Stand-alone inline particle inspection (primary data); line cleanliness (customer facility) | (1) put fail_frac itself on the `FAIL_FRAC_MEAN` chart: gradual rise → line contamination, single lot → that lot's history; (2) clustering → it is LOC / EDGE_LOC (isolated_frac, hypothesis); (3) inline particle trend per step; (4) TEL chamber: post-PM particles, wafers since seasoning; (5) before/after a cleaning-tool change | Wrong design assumption (n_comp AUC 0.155); F1 0.90 |
| NEAR_FULL (most of the wafer failing) | Process incident or test cause. **Rule out the test side first**: probe-card planarity, overdrive, contact resistance (CRES), test-program limits, product/wafer-ID mix-up all print as full failure; tip contamination raising CRES recovers after cleaning sheets / scrub. Then abnormal termination in the lot history (recipe error, skipped step, tool down). Broken wafers usually never reach test (estimate) | Precio / Prexa: probe-card contact, cleaning, touchdown counter. All TEL process tools: alarm/event logs, recipe abort records | Test program / tester; other vendors' process tools that aborted | (1) **retest** (planarity, overdrive, CRES, limits, ID); (2) other wafers of the same lot (process incident) or one wafer (single event); (3) lot history abnormal termination vs tool alarm logs; (4) if confirmed, line-stop / lot-hold decision together with the customer yield team (initial report); (5) handling alarm logs if breakage is suspected | fail_frac AUC 1.000; F1 0.98; 149 wafers. Operations prioritize **recall**: a miss delays the line-stop decision, a false alarm costs one retest |

The cost of misclassification is discussed per confusion pair in [`defect_signatures.md`](defect_signatures.md) ("오분류의 현장 비용"): e.g. LOC read as EDGE_LOC sends the engineer to robot centering instead of particle sources and lift pins; SCRATCH read as LOC skips the transfer-system check; a missed NEAR_FULL is the most expensive error, so a `fail_frac` hard rule precedes the classifier and low-confidence wafers are reviewed by a person.

## 6. SPC on top of the classifier (`wm811k_spc.py`)

The classifier judges one wafer; this script is the stage above it. Predictions are grouped into subgroups in time order and the question is "is the rate of this pattern rising?" — the one-directional drift (consumable wear, chamber contamination build-up) that single-wafer judgment cannot see. In industry terms: per-pattern p-charts are a fault-detection indicator built from result data instead of tool sensors; Phase I/II = limit setting / monitoring; EWMA = run-to-run drift monitoring; the low-confidence chart = model-drift monitoring. Tool-side FDC/APC software (for TEL, Ingenio is the APC/FDC trademark and TELeMetrics the remote monitoring service, per 2015 press) handles sensor data; this script handles result data, and `--time-col` / `--event-col` put the two on one time axis. TEL internals are unknown. Details and all demo numbers: [`spc.md`](spc.md).

- **Per-pattern p-charts** with limits recomputed per subgroup size; rare patterns get subgroups enlarged automatically so that n·p̄ ≥ 5 and n·(1−p̄) ≥ 5. The x-axis is the wafer index, so charts with different subgroup sizes share one axis.
- **Occurrence vs share.** If the prediction CSV contains CLEAN/none the denominator is all inspected wafers (occurrence-rate chart); otherwise it is defect wafers only (share chart), whose rates sum to 1 so a rising pattern mechanically pushes others down. The mode is detected automatically and downward alarms are excluded from the check list by default (`--up-only`).
- **Laney p′** overdispersion correction: wafers of one lot share patterns, so between-lot variation exceeds binomial variance and plain p-charts keep false-alarming. σz = mean moving range of baseline z-scores / 1.128; limits are widened by σz. Skipped when the baseline has fewer than 20 subgroups; σz < 1 is clamped to 1 (a deliberate conservative deviation from Laney's original).
- **Rules**: Western Electric R1–R4 and EWMA (λ 0.2, L 2.86 — the ARL0 ≈ 500 pair per Lucas & Saccucci 1990 tables, not re-verified from the original). Limits come from the first 50% (baseline); a baseline alarm rate above 5% triggers a warning that the data are not in time order or not stable.
- **Low-confidence chart**: fraction of wafers below a confidence threshold taken as a baseline quantile (`--conf-quantile`, default 0.10) rather than a fixed value, because the probability distribution depends on model and class count. `confidence` = RF `predict_proba` maximum from `wm811k_validate.py --export-predictions` (uncalibrated); the rule classifier's `score` is accepted as an alias with a warning.
- **Field options**: `--group-col chamber|tool|slot` (stratified charts `EDGE_RING@B` plus chi-square between groups), `--event-col` (PM / part-replacement vertical lines and distance from first detection to the nearest earlier event), `--anonymize` (lot and group IDs replaced by keyed hashes, no mapping saved), `--lang en`. Outputs: chart PNG, subgroup CSV, alarm CSV with field columns (`acknowledged_at`, `action`, `verified_at`), and a human-readable alarm report `spc_<stem>_report.md`.
- **Demo** (synthetic, logic only): 6,000 wafers / 240 lots / chambers A–B; EDGE_RING drift planted in chamber B from wafer 3000 (first detected by R3 at 3799 overall, by R4 at 3574 stratified), low confidence from 3750 (R3 at 3849), a SCRATCH step from 4125 (R1/EWMA at 4499). Baseline false-alarm rate 0 %, 3 rising false alarms among 131 monitored points in the stratified run.
- **Not usable on WM-811K itself**: its row order is product/lot block order, not time; the script detects this and warns.

## 7. Files

| File | Role |
|---|---|
| `wafer_pattern_classifier.py` | Rule classifier (8 patterns) + action playbook `ACTION_DETAIL` (single source for docs, PDFs and SPC alarm text). `--actions <PATTERN>` |
| `wafer_map_visualizer.py` | Synthetic wafer-map generator and renderer; WM-811K 2D array → die DataFrame |
| `wm811k_evaluate.py` | Uncalibrated rule evaluation on real data, feature AUCs, lot-size distribution, writes `wm811k_predictions.csv`. `--with-none` |
| `wm811k_calibrate.py` | Threshold calibration on train lots + decision-tree / RF baselines |
| `wm811k_structural.py` | 11 structural features (connected components, angular coverage, radial profile) and comparison |
| `wm811k_validate.py` | 5-seed lot-split validation, 3 position features, RF regularization. `--export-predictions` → `test_predictions.csv` |
| `wm811k_improve.py` | 8 noise-robust features + HistGradientBoosting, paired on the same 5 splits (not measured on real data) |
| `wm811k_spc.py` | SPC on predictions: Laney p-charts, low-confidence chart, WE rules, EWMA, `--group-col` / `--event-col` / `--anonymize` / `--lang`, alarm report |
| `wm811k_azimuth.py` | Notch-relative azimuth of EDGE_LOC / LOC within a lot, Rayleigh test with permutation p. `--notch-deg` |
| `wm811k_scratch_shape.py` | Line vs arc fit of the largest component; within-lot direction reproducibility |
| `wm811k_slot.py` | Slot (waferIndex proxy) dependence: end-slot 2×2, lot-stratified permutation test, Spearman trend |
| `wm811k_commonality.py` | Tool commonality from a lot-history CSV: within-step Fisher test, BH correction, routing overlap warning |
| `wm811k_lot_report.py` | Lot troubleshooting report PDF + JSON: mix, repetition, azimuth, shape, slot, commonality, suspect ranking, OCAP level, 8D-D2 draft |
| `batch_wafer_report.py` | Batch PDF + one-page service-report form per lot. `--lang en`, `--anonymize`, `--service-report` |
| `plotly_wafer_heatmap.py` | Parametric (thickness / CD) wafer map as self-contained offline HTML. `--csv` (die_x, die_y, value) |
| `prepare_wm811k.py` | Extract labeled wafers from LSWMD.pkl. `--sample N` (by lot) |
| `make_figures.py` | Regenerates every figure and sample PDF in `docs/img` and `docs/samples` from synthetic data. `--only`, `--lang en` |
| `_fonts.py` | matplotlib Korean font: bundled NanumGothic first, then system fonts, one warning otherwise |
| `PORTFOLIO.md` | What the repository proves and does not prove; six technical questions it answers |
| `docs/defect_signatures.md` | Per-pattern mechanism, TEL modules / hand-off, customer- vs tool-side evidence, check order, cost of misclassification, field procedure |
| `docs/tel_equipment_map.md` | Process area → current TEL product → consumables/PM (estimates marked) → patterns; join keys to tool-side data |
| `docs/process_context.md` | Signatures by process step, six tool subsystems, safety / cleanroom checklist before touching a tool |
| `docs/handoff.md` | TEL cause vs hand-off criteria, three-stage customer reporting, 8D team roles, customer-data confidentiality |
| `docs/case_study_8d.md` | Two synthetic 8D cases (EDGE_RING drift, SCRATCH step): timeline, 5-why, report examples, recovery after action |
| `docs/spc.md` | SPC details: occurrence vs share, automatic subgroups, Laney, EWMA parameters, demo detection times, column dictionary |
| `docs/validation_log.md` | Experiments 0–8 (hypothesis → script → numbers → conclusion), design principles, number-freeze rule |
| `docs/roadmap.md` | Verification scope per feature (real / synthetic / unmeasured) and remaining items |
| `docs/glossary.md` | Equipment, defect, quality and statistics terms in Korean / English / Japanese |
| `docs/lot_history_schema.md` | Input CSV schema for commonality analysis (fictitious IDs) |
| `docs/references.md` | Every external claim with source, check date and verification level |
| `docs/img/`, `docs/samples/`, `docs/fonts/` | Synthetic figures and flow chart, two sample PDFs, NanumGothic (SIL OFL 1.1) |
| `tests/` (13 files) | Synthetic-only pytest suite: feature snapshot (number-freeze guard), action playbook consistency, exports, SPC, azimuth, scratch shape, slot, commonality, lot report, PDF report, figures, end-to-end pipeline |
| `results/`, `data/README.md`, `.github/workflows/test.yml` | Reproduction artifacts of the measured numbers (to be filled by the owner), data acquisition notes, CI (ubuntu / windows × Python 3.11 / 3.12) |

## 8. Running

Python ≥ 3.10 (CI uses 3.11 / 3.12). On Windows every script switches the console and file redirection to UTF-8 itself; the Korean font is bundled in `docs/fonts/`. Data path via `WM811K_DIR`; outputs are written next to the scripts and ignored by git.

```bash
pip install -r requirements-dev.txt
# (1) Five minutes without data - all synthetic (logic checks, not performance)
python wafer_pattern_classifier.py                                   # synthetic self-check 7/7, exit code 1 on failure
python -m pytest -q                                                  # whole tests/ (about 2 minutes)
python batch_wafer_report.py --lang en --anonymize                   # batch PDF + service-report form
python wm811k_spc.py --demo --group-col chamber --event-col event --lang en   # charts, alarm CSV, alarm report (spc/)
python wm811k_lot_report.py --demo --lang en                         # lot troubleshooting report PDF + JSON
python wm811k_azimuth.py --demo && python wm811k_scratch_shape.py --demo && python wm811k_slot.py --demo && python wm811k_commonality.py --demo
python make_figures.py --lang en                                     # regenerate docs/img, docs/samples (English labels, _en suffix)
# (2) Real data - needs data/LSWMD.pkl (about 2 GB, see data/README.md). Times are 4-core estimates
python prepare_wm811k.py                                             # -> data/wm811k_defects.pkl (minutes)
python wm811k_evaluate.py                                            # uncalibrated rules 0.167, wm811k_predictions.csv (feature extraction ~2 min)
python wm811k_calibrate.py                                           # calibrated 0.558 + tree comparison (minutes)
python wm811k_structural.py                                          # structural features -> RF 0.878 (minutes)
python wm811k_validate.py --export-predictions                       # 0.907 +- 0.008 + test_predictions.csv (~10 min)
python wm811k_improve.py                                             # 8 robust features + HGB, not yet measured (~5 min)
```

## 9. Limits and data handling

- Only **public data (WM-811K) and synthetic data** live in this repository. No customer data, no real tool or chamber identifiers; reports and charts have `--anonymize`; every sample report, figure and case study is synthetic ([`handoff.md`](handoff.md) §4).
- WM-811K lacks timestamps, tool/chamber IDs, slots (waferIndex is only a proxy), probe sites / touchdowns and exposure-field information. SPC, commonality, slot, azimuth and lot-report modules are therefore synthetic logic checks; their real-data effect is unmeasured ([`roadmap.md`](roadmap.md) §1 lists the verification scope per feature).
- Notch orientation is an assumption (`notch_deg = -90`, the plotting convention); only relative angles within a lot are interpreted.
- The defect subset averages 3.2 wafers per lot (25,519 / 8,047), so most lot-level tests return `insufficient`.
- Row order is not time order, so SPC cannot be applied to WM-811K itself.
- Classifier: remaining confusions LOC → EDGE_LOC (542) and SCRATCH → LOC (270); the 147,431 `none` wafers are excluded, so the "is there a pattern at all?" gate is unmeasured; train/test gap 0.99 / 0.91; `wm811k_improve.py` unmeasured; map sizes (329) have unknown physical dimensions, so all radii are ratios; no CNN / image-based model was tried.
- Equipment statements are public-source level (product pages, patents, papers, textbook process physics). TEL internal structures, manuals and PM intervals are unknown; "(estimate)" marks unverified items; community-sourced claims are not used.

## 10. Sources and license

WM-811K — Wu, M.-J., Jang, J.-S. R., & Chen, J.-L. (2015). *Wafer map failure pattern recognition and similarity ranking for large-scale data sets.* IEEE Transactions on Semiconductor Manufacturing, 28(1), 1–12. MIR Lab, National Taiwan University. Secondary distribution: Kaggle "WM-811K wafer map" (license to be confirmed by the owner and recorded in [`../data/README.md`](../data/README.md)). The source file is not included. All other claims: [`references.md`](references.md).

License: code MIT ([`../LICENSE`](../LICENSE)); bundled font NanumGothic under SIL OFL 1.1 ([`fonts/OFL.txt`](fonts/OFL.txt)); data under the terms of each source.
