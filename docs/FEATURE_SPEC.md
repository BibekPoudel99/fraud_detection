# FEATURE_SPEC.md — features, shared function, and state handling

**Status:** Draft 0.2, updated 5 Nov 2026 after the EDA run. **Owner:** Bibek. **Feature schema version:** `0.2.0` (becomes `1.0.0` after the real-data parity run, S1-09; see section 9).
**Feeds:** `docs/API_CONTRACT.md` (feature names and `feature_schema_version`), the EDA/split notebook, the model-training notebook, the Flow A fraud consumer, and Flow C batch scoring.

**Read this first.** The gates in section 7 were pre-registered (keep/drop rule fixed before the numbers were seen) and have now been run on the real data (results in section 9). **Gate G2 failed**, so the four origin-side "transfer-then-cash-out" features were dropped and the schema went from 0.1.0 (16 features) to 0.2.0 (12 features). Everything else survived.

---

## 1. Decisions and rationale

| # | Decision | Why (viva-ready) | Alternative rejected |
|---|---|---|---|
| D1 | **One feature function for training, Flow A and Flow C**, split into two pure pieces: `compute_features(event, dest_state)` (read-only) and `update_dest_state(event, dest_state)` (returns the next state). Both live in `shared/features/` and are imported everywhere. | Training/serving skew is the standard way a "real-time" model silently underperforms. One implementation makes the two paths identical by construction, and a parity test (section 6) proves it on real data. | A vectorised pandas version for training plus a streaming version for the workers: faster to run, but two implementations of every feature. |
| D2 | **Score first, then update state; history means only events processed earlier.** The event model has no label field. | Structural leakage guard: an event can never see itself or its own label, and the state can never contain a future event. Tests 3 and 4 try to break this. | Relying on convention ("remember not to use the label"). |
| D3 | **Only `TRANSFER` and `CASH_OUT` are scored** (the other three types never reach `/predict`). **Confirmed (section 10).** | PaySim's fraud label appears only on those two types (README sections 1 and 7), so a model has nothing to learn about the other three and any score on them would be meaningless. It also matches the locked detection scope. | Scoring all five types: dilutes the base rate and implies a claim the data cannot support. |
| D4 | **State is "inbound `TRANSFER` credits per account", read for the recipient only.** No per-origin state and no per-origin spending history. | Confirmed by gate G1 on the real data: 6,353,307 distinct `nameOrig` values in 6,362,620 rows (99.85% distinct), so per-origin history is empty for almost every row. Gate G2 then showed the origin-side chain (did the sender just receive a transfer?) carries no signal, so the state now serves only the recipient-side fan-in features. Memory grows with distinct *recipients*. | Full per-account history for all 6M+ origins: large memory, mostly-degenerate features. |
| D5 | **Features for the whole dataset come from one chronological pass; the splits are cut afterwards by row position.** State carries across split boundaries. | Production works this way: a transaction in the test period is scored with history that includes earlier (training-period) events. Each row's features still use only earlier rows, so there is no leakage. | Recomputing features per split from empty state: test rows would look like cold-start accounts, unlike anything in production. |
| D6 | **Flow A starts with state primed from the batch pass, for the accounts that appear in the replay pool only.** | Priming makes replay features *exactly equal* to the batch features for the same rows (test 6), so live-demo numbers and the reported test-style numbers are computed the same way. Only accounts in the replay pool matter, because a row's features depend only on the recipient's state, so only recipient accounts of the replay pool need priming and memory stays small. | Cold start: every account looks new at the start of the replay, which is a demo artefact, not behaviour. |
| D7 | **Flow C starts from empty state**, over the uploaded file only, sorted by `step` (stable). | An uploaded file carries no earlier history. The history features are therefore weaker in Flow C than in Flow A. This is a stated limitation, not hidden. | Looking up history for uploaded rows in Redis/Postgres: it would mix an uploaded file with live state. |
| D8 | **No missing values, ever.** Every feature is defined for every scored row, with an explicit sentinel and, where a sentinel could be ambiguous, a companion flag. | The API contract rejects NaN, and imputation by the model service would be a second implementation of feature logic. | NaN passed through to XGBoost: works, but Logistic Regression would need a separate path. |
| D9 | **Fitted preprocessing (e.g. the Logistic Regression scaler) lives in the model artifact, not in this function.** | Scaler parameters are learned from the training split; this function holds only stateless, deterministic logic. (Same boundary as `API_CONTRACT.md` section 2.) | Fitting a scaler in the shared function: it would leak validation/test statistics or need its own versioning. |

## 2. Column by column

PaySim has 11 columns. Descriptions are from the dataset documentation as reproduced in a [secondary source](https://medium.com/@lukewago/financial-datasets-for-fraud-detection-af20be29ffbc); the Kaggle page itself did not render for me, so column *spellings and behaviour* are confirmed only by your own `data_loader.py` output and the EDA gates.

| PaySim column | Documented meaning | Role in the feature function | Rationale |
|---|---|---|---|
| `step` | One step = 1 hour; 744 steps (30-day simulation) | **State clock only.** Used for window arithmetic (`current step − credit step`). **Not** a model feature. | A raw step lets a tree memorise *when* in the 30 days fraud happened. That is a property of one simulation run and not behaviour. |
| `type` | `CASH_IN`, `CASH_OUT`, `DEBIT`, `PAYMENT`, `TRANSFER` | Scope gate (D3) and feature `type_is_transfer`. | Scope is TRANSFER/CASH_OUT, so one binary feature carries all the type information. |
| `amount` | Transaction amount, local currency | `log_amount`; numerator of the two ratio features. | Heavy-tailed; log keeps Logistic Regression stable. Trees are unaffected. |
| `nameOrig` | Customer who started the transaction | **State key only**, never a feature. Looked up to read the sender's inbound-credit state. | An identifier. Using it as a feature would let a model memorise accounts. |
| `oldbalanceOrg` | Sender balance before | `log_orig_balance_before`, `amount_to_orig_balance`, `orig_balance_zero`, balance-error feature. | Balance-relative size is the available proxy for "inconsistent with the account's profile" (section 4). |
| `newbalanceOrig` | Sender balance after | `orig_drained`, `orig_balance_error`. | "Account emptied" is the fund-draining signature of the scoped fraud type. |
| `nameDest` | Recipient. Names starting with `M` are merchants and carry no balance information | **State key only.** | As `nameOrig`. Gate G4 checks that merchants never appear as recipients of `TRANSFER`/`CASH_OUT`; if they do, add a `dest_is_merchant` feature. |
| `oldbalanceDest` | Recipient balance before | `dest_old_balance_zero`, `dest_balance_error`. | Balance-consistency group, see the ablation note in section 3. |
| `newbalanceDest` | Recipient balance after | `dest_new_balance_zero`, `dest_balance_error`. | As above. |
| `isFraud` | Transactions made by the simulation's fraudulent agents, which "take control of customer accounts" | **Label only.** Not in `TransactionEvent`, not in the state, never in a request. | Label leakage guard (D2). |
| `isFlaggedFraud` | Flags an "illegal attempt": a single transfer above 200,000 | **Excluded from features.** Used as rule baseline **R1** in the model comparison (section 6.1). | It is the simulator's own business rule over `amount`, so as a feature it is redundant at best and a leak of simulator logic at worst. |

## 3. Feature catalogue (12 features, schema 0.2.0)

Constants (single frozen config, a change bumps the schema version): `window_steps = 24`, `ratio_clip = 10.0`. Both are **starting values** to confirm in EDA. "Window" means events with `current_step − credit_step < 24`, so same-step earlier events count.
Helpers: `log1p_nn(x) = log(1 + max(x, 0))`; `signed_log1p(x) = sign(x) · log(1 + abs(x))`; `ratio(a, b) = min(a / b, ratio_clip)` if `b > 0`, else `0`.

| # | Feature | Definition | Group | Maps to |
|---|---|---|---|---|
| 1 | `type_is_transfer` | 1 if `TRANSFER`, 0 if `CASH_OUT` | stateless | scope |
| 2 | `log_amount` | `log1p_nn(amount)` | stateless | — |
| 3 | `log_orig_balance_before` | `log1p_nn(oldbalanceOrg)` | stateless | red flag 4 (partial) |
| 4 | `amount_to_orig_balance` | `ratio(amount, oldbalanceOrg)` | stateless | red flag 4 (partial) |
| 5 | `orig_balance_zero` | 1 if `oldbalanceOrg == 0` | stateless | companion flag to #4 |
| 6 | `orig_drained` | 1 if `oldbalanceOrg > 0` and `newbalanceOrig == 0` | stateless | fund-draining scope |
| 7 | `orig_balance_error` | `signed_log1p(oldbalanceOrg − amount − newbalanceOrig)` | **balance-consistency** | — |
| 8 | `dest_balance_error` | `signed_log1p(oldbalanceDest + amount − newbalanceDest)` | **balance-consistency** | — |
| 9 | `dest_old_balance_zero` | 1 if `oldbalanceDest == 0` | **balance-consistency** | — |
| 10 | `dest_new_balance_zero` | 1 if `newbalanceDest == 0` | **balance-consistency** | — |
| 11 | `dest_inbound_transfer_count_24h` | number of inbound `TRANSFER`s to the **recipient** in the window (fan-in) | stateful | — (mule-style recipient) |
| 12 | `dest_has_prior_inbound_transfer` | 1 if the recipient has *ever* received a `TRANSFER` before | stateful | weak proxy only, see section 4 |

Notes:
- **Sentinels.** None needed now: the count features use `0` for "none", and the flags are 0/1. (The dropped origin-side features had used `24` as a sentinel.)
- **Dropped in 0.2.0 (gate G2):** `orig_inbound_transfer_count_24h`, `log_orig_inbound_transfer_sum_24h`, `steps_since_orig_last_inbound_transfer`, `amount_to_orig_inbound_sum`. See section 7 and 9.
- **Balance-consistency group (#7 to #10) carries a simulator-artefact risk.** In a real payment system a balance mismatch would mean something different; in PaySim it may simply reflect how the simulator writes balances, and these features are known to be strongly predictive in public PaySim notebooks. **Required experiment:** every model in the comparison table is reported with and without this group, so any headline number is not inflated by a simulator quirk, and the viva answer to "does it transfer?" is evidence, not opinion.
- **Self-transfer** (`nameOrig == nameDest`): both states are read before the update, so a transfer never sees its own credit.

## 4. FIU-Nepal red flags: what is and isn't represented

The five red flags below are the ones listed in README section 2 (from the verified FIU-Nepal 2024 report). The honest claim for the report is **"informed by"**, with the mapping stated flag by flag:

| FIU-Nepal red flag | Representable in PaySim? | How |
|---|---|---|
| Multiple accounts opened under one identity | **No** | PaySim has no identity field. |
| Rapid transactions shortly after account opening | **No (not faithfully)** | There is no account-opening date. "First seen in the dataset" is an artefact of where the 30-day window starts, and with near-unique origins it is almost always true. #12 ("recipient never received a transfer before") is a *weak* proxy for a fresh recipient account and must not be described as account age. |
| Transfer followed by immediate withdrawal | **No (gate G2 failed)** | The candidate features (did the account now cashing out just receive transfers?) were dropped: none of the 1,826 fraud cash-outs in the train split follows an inbound transfer to the same account within 24 steps. Not operationalised. |
| Behaviour inconsistent with the account holder's economic profile | **Partially** | Balance-relative size (#3, #4, #6) only. No per-account history (D4). |
| Geographic / device anomalies | **No** | No location or device fields. |

**Claim wording for the report (after G2):** *"The features partially represent one of the five FIU-Nepal red flags (behaviour inconsistent with the account holder's profile, through balance-relative size). Transfer-then-immediate-withdrawal could not be operationalised because PaySim does not link the two legs at the account level (EDA gate G2); the other three cannot be represented in PaySim. All are listed as limitations."*

## 5. The shared function

### Signatures (`shared/features/core.py`, full code in Appendix A)

```python
FEATURE_SCHEMA_VERSION: str                 # "0.2.0"
FEATURE_NAMES: tuple[str, ...]              # fixed order; equals the model artifact's feature_names
SCORED_TYPES = {"TRANSFER", "CASH_OUT"}

class TransactionEvent(BaseModel): ...      # snake_case PaySim fields, NO label, extra="forbid"
@dataclass(frozen=True)
class AccountState:                         # inbound credits inside the window + lifetime count
    inbound: tuple[tuple[int, float], ...]
    inbound_total: int

class StateStore(Protocol):
    def get(self, name: str) -> AccountState: ...   # empty state if unknown; must not create
    def put(self, name: str, state: AccountState) -> None: ...

def compute_features(event, dest_state, cfg=CONFIG) -> dict[str, float]               # read-only
def update_dest_state(event, dest_state, cfg=CONFIG) -> AccountState                  # next state
def process_event(event, store, cfg=CONFIG) -> dict[str, float] | None               # compute, then update
def build_feature_table(df, store=None, cfg=CONFIG) -> (DataFrame, StateStore)         # batch driver
```

`process_event` is for **training and Flow C**. The **Flow A worker uses `compute_features` and `update_dest_state` separately**, because it has to call `/predict` and write to the database between them (below). It is the same two functions, so parity holds.

### Using it in the training notebook

```python
from data_loader import load_paysim
from shared.features import build_feature_table, FEATURE_SCHEMA_VERSION

df = load_paysim()                          # original CSV row order
feats, store = build_feature_table(df)      # ONE chronological pass over all rows
feats.to_parquet(f"data/cache/features_v{FEATURE_SCHEMA_VERSION}.parquet")   # gitignored cache
y = df.loc[feats.index, "isFraud"]
# cut train / val / test / replay by ROW POSITION of df (README 7.1), then select feats.index within each
```

### Ordering rules (these are what make the claims true)

1. Input order is the **original CSV order**, with `step` non-decreasing. `build_feature_table` raises if it is not. Events inside one step are processed in row order.
2. The replay producer emits events in that same order from a **single producer**.
3. The Flow A fraud consumer must be a **single consumer instance** (one `XREADGROUP` consumer). State depends on order, so parallel consumers on one stream would reorder events and silently change features. (A scaled-out version would partition by account; that is future work.)

### Flow A worker sequence (exactly-once effect on state, at-least-once delivery)

For each stream event, in this order:

1. `compute_features` from the stored recipient state (read only). Out-of-scope type: skip to step 5.
2. `POST /predict` (retry rules in `API_CONTRACT.md` section 8).
3. Write the prediction to `fraud_predictions` (unique on `(transaction_id, model_version)`, so a repeat insert is a no-op). Also store the feature vector with the row (a `features` JSONB column) so any prediction can be explained later.
4. If `/predict` failed permanently, dead-letter the event.
5. **In one Redis transaction (`MULTI`/`EXEC`):** write the new recipient state from `update_dest_state` **and** `XACK` the message. Do this on the dead-letter path too, so one bad event cannot desynchronise later features.

A crash before step 5 means redelivery: features are recomputed from the unchanged state (deterministic), the database insert is a no-op, and the state update then happens exactly once.

**Redis layout (suggestion):** key `acct:{name}`, value `json.dumps({"inbound": [[step, amount], ...], "total": n})`. Python's JSON round-trips floats exactly, which is what test 5 checks.

### Priming (D6), done by your ETL

After the batch pass over the rows *before* the replay pool, copy `store.get(name)` into Redis for every `name` in `{nameDest}` of the replay-pool rows (features read the recipient only), and record it in `etl_runs`. Test 6 shows this reproduces batch features exactly (synthetic data; you will repeat it on real data).

## 6. Tests and acceptance criteria

`tests/test_features.py` (13 feature tests; 30 with the API schema tests, pass on synthetic data in my sandbox; **the real-data runs below are yours**). Mutation checks: deliberately updating state before scoring, or moving the window boundary by one step, each make tests fail.

| # | What it proves |
|---|---|
| 1 | Hand-computed recipient-side values (fan-in count, lifetime flag) are as expected. |
| 1b | The dropped origin-side features stay dropped (12 names, none containing `orig_inbound`). |
| 2 | Window boundary: a credit 23 steps old counts, 24 steps old does not. |
| 3 | **No future leakage:** features for the first *k* rows are identical when only the first *k* rows exist, and when every later row is altered. |
| 4 | **Label independence:** flipping `isFraud` and `isFlaggedFraud` changes no feature; the event model rejects an `isFraud` field. |
| 5 | Batch pass equals streaming through a store that round-trips state via JSON (Redis stand-in), bit for bit. **Run this same test against your real Redis store.** |
| 6 | State primed at the replay boundary (only recipient accounts in the tail) reproduces the batch features for the tail, bit for bit. |
| 7 | All outputs finite; columns equal `FEATURE_NAMES` in order; only scored types; ratios within the clip. |
| 8 | Out-of-order input rejected; out-of-scope type cannot be scored; self-transfer reads state before update; NaN event rejected. |

**Real-data acceptance criteria (for the training notebook and workers):**
- Test 6 repeated on the real replay pool: maximum absolute difference between batch and primed-stream features is `0.0`.
- Feature table is finite and has exactly `FEATURE_NAMES` columns.
- Feature parquet file name carries `FEATURE_SCHEMA_VERSION`; the model artifact stores the same string.

**Cost.** On 300,000 synthetic events in my sandbox the batch pass ran at about 80,000 rows per second, which would put the 6.36M-row pass at roughly a minute or two. Real rows and your machine will differ, so treat it as an order of magnitude and cache the result. State memory grows with distinct *recipients of transfers*. Measure peak memory on the first 1M real rows before running the full pass.

### 6.1 Rule baselines (extra rows in the model comparison table)

**Purpose.** Show what static rules achieve on the same rows as the ML models. This supports the problem statement (README section 2) that rule-based engines are rigid, and it tests our own hypothesis of what the fraud looks like (an account-draining move of a large amount).

| Row | Rule (predict fraud when...) | Source of the rule |
|---|---|---|
| **R1** | `isFlaggedFraud == 1` | The simulator's own flag, used exactly as supplied. Never a model feature. Observed behaviour (G7): the flag is set on only 16 rows of 6.36M, so it is expected to have near-zero recall. |
| **R2** | type is `TRANSFER` or `CASH_OUT`, **and** `oldbalanceOrg > 0` and `newbalanceOrig == 0` (the account is drained; equals feature `orig_drained == 1`) | Our drain hypothesis. |
| **R3** | R2 **and** `amount > 200,000` | Drain + bulk. The 200,000 figure is borrowed from PaySim's documentation, **not tuned on our data**. Train-split exploration (3,633 fraud, 5 Nov 2026): R2 recall 0.979, precision 0.004 (TP 3,558, FP 818,744); R3 recall 0.636, precision 0.006 (TP 2,309, FP 417,409). The filter halves false positives but loses a third of the fraud. Final R1 to R3 numbers come from the test split (S1-11). |

Rules for using them:
1. All three are fixed here, before the test split is read. Nothing is tuned on the test split.
2. They output yes/no, not a score, so report precision, recall, F1 and the confusion matrix; PR-AUC is "n/a (no score)".
3. Same test rows and same denominator as the ML models (gate G6).
4. If a one-line rule (R2 or R3) comes close to XGBoost, **say so in the report.** It is a finding about how simple PaySim's fraud is, and it feeds the artefact-risk discussion in section 3. Do not hide it.

## 7. EDA gates (decision rules fixed in advance)

Run these first in the EDA notebook. Record the numbers in this file (section 9) when you freeze the schema.

| Gate | Question | How | Rule |
|---|---|---|---|
| **G1** | Do origin accounts repeat? | Share of `nameOrig` values appearing in more than one row. | If still ~99.85% distinct: D4 stands. If a material share repeats: add per-origin history features in 0.2.0. |
| **G2** | Does the transfer-then-cash-out chain exist **at the account level** in this data? | Among `CASH_OUT` rows **in the train split only**, the share whose `nameOrig` received a `TRANSFER` in the previous 24 steps, **for fraud rows vs legitimate rows**. | If the share is not materially higher for fraud rows (for example it is near zero for both), features #11 to #14 cannot carry signal. Drop them, keep the rest, and in the report say the label encodes the scope but the account-level chain is not recoverable from PaySim. Do **not** claim FIU red flag 3 as operationalised (section 4). |
| **G3** | Is the CSV in `step` order? | `df["step"].is_monotonic_increasing`. | Must hold; otherwise the whole chronological design is void. |
| **G4** | Are merchants ever recipients of `TRANSFER`/`CASH_OUT`? | Count `nameDest` starting with `M` in those types. | The secondary notebook I found reports none. If any exist, add `dest_is_merchant`. |
| **G5** | Self-transfers | Count `nameOrig == nameDest`. | Informational; the function already handles it. |
| **G6** | Base rates and denominators | Fraud count and rate over **all rows** and over **`TRANSFER` + `CASH_OUT` only**. | Every reported metric states which denominator it uses. The scoped rate is higher than the dataset-wide ~0.13%, and PR-AUC depends on it. |
| **G7** | `isFlaggedFraud` | Count of 1s, and whether they are all transfers above 200,000 (all rows); how R1 behaves on the **train** split. | Confirms the documented rule; informs rule baseline R1. |

**How the gates are run (`notebooks/01_eda_and_split.ipynb`).**
- **Label-free gates** (G1, G3, G4, G5) run on all rows. **Anything that reads `isFraud` to decide a design question (G2, G7, the exploration section) runs on the train split only**, so no feature decision is informed by validation, test or replay labels. G6 only counts rows and frauds per split.
- **"Material" and "signal" need numbers, so the notebook fixes them in its first cell before any output is seen:** G1 revisits per-origin history if at least 5% of scoped rows have a repeated origin; G2 keeps features 11 to 14 only if at least 5% of fraud cash-outs have an inbound transfer in the previous 24 steps **and** that share is at least 2 times the share among legitimate cash-outs. Change them only before the first run, and commit the change.
- **Split mechanics:** cut by row position in the original order at about 70 / 15 / 10 / 5 percent (train / validation / test / replay), each cut snapped to the start of a `step` so no step is shared between two splits. No randomness is used. Boundaries are saved to `docs/split_boundaries.json`.

## 8. Deferred or excluded (with reasons)

| Item | Why not in 0.2.0 |
|---|---|
| `hour_of_day` (`step % 24`) | README 5.17 already warns that timing norms in PaySim (modelled on an African mobile-money context) may not transfer to Nepal; add only as an ablation candidate. |
| Per-origin history (count, amount vs own mean, time since first seen) | Gate G1 and D4. |
| Distinct senders to a recipient | Needs a set per account (heavier state). Candidate for a later version if #11 proves useful. |
| Origin-side inbound-transfer features (4) | **Dropped in 0.2.0**: gate G2 failed on the real train split (no signal). Revisit only with real, account-linked data (README 11.1). |
| Raw `step`, account names, `isFlaggedFraud`, `isFraud` | Section 2. |

## 9. Change policy and freeze

- **Freeze:** gates G1 to G7 are run and recorded below. The version becomes `1.0.0` after the real-data parity run (test 6 on the real replay pool, S1-09). Until then the schema is `0.x` and the API contract's `1.0.0` examples are illustrative.
- **Any** change to `FEATURE_NAMES`, a formula, `window_steps` or `ratio_clip` bumps `FEATURE_SCHEMA_VERSION`: MAJOR for a removed/renamed/redefined feature, MINOR for an added one, PATCH for no change in output (refactor only). The model artifact stores the version; `/predict` returns 409 on a mismatch (`API_CONTRACT.md`).
- Changes go through a PR that updates this file and `shared/features/` together.

**Gate results (real data, run 5 Nov 2026 with `notebooks/01_eda_and_split.ipynb`; 6,362,620 rows; boundaries in `docs/split_boundaries.json`):**

| Gate | Result | Consequence |
|---|---|---|
| G1 | 6,353,307 distinct `nameOrig` (99.8536%); 0.2930% of scoped rows have a repeated origin (cutoff 5%) | D4 stands; no per-origin history. G1b: 77.5% of TRANSFER rows have a recipient that receives more than one transfer, so recipient fan-in is non-degenerate. |
| G2 (train) | 1,826 fraud cash-outs: **0%** follow an inbound transfer to the same account in 24 steps; legitimate: 0.0011% of 1,569,816. Fraud TRANSFER recipients that later cash out: 0%. Only 131 accounts are both a transfer recipient and a cash-out sender. Lift 0.00 (rule: share >= 5% and lift >= 2) | **Failed. Features 11 to 14 dropped; schema 0.2.0.** FIU red flag 3 not claimed. |
| G3 | Pass: steps 1 to 743, monotonic, 743 distinct | Chronological design valid. The simulation has 743 steps in this file, not 744. |
| G4 | 0 merchant recipients on scored types | No `dest_is_merchant` feature needed. |
| G5 | 0 self-transfers | Informational. |
| G6 | 8,213 frauds: 0.1291% of all rows, 0.2965% of scoped rows. Fraud is roughly 11 per step in every split while volume per step falls, so **base rates differ strongly between splits** (the replay pool is the most inflated, 2.07%) | Every metric states its split's base rate; precision and PR-AUC are not comparable across splits. |
| G7 | 16 flagged rows in total; R1 on train: TP 3, FP 0, FN 3,630 | R1 is expected to be near-useless as a detector (documented rule and observed behaviour do not match). Report it as is. |

## 10. Decisions

**Resolved (2 Nov 2026):**
1. **D3, scope gate:** only `TRANSFER` and `CASH_OUT` are scored. Confirmed with the locked scope statement.
2. **Rule baselines:** `isFlaggedFraud` (R1) and the drain rules (R2, R3) are rows in the comparison table (section 6.1).
3. **Claim wording, locked:** the platform is demonstrated on the account-takeover transfer-then-cash-out pattern using synthetic PaySim data. Applicability to Nepali mobile-banking and wallet traffic is future work and needs a real Nepali dataset and a model trained on it (goes in README 11.1 and section 10).

**Resolved (5 Nov 2026), after the EDA run:**
4. **G2 failed:** features 11 to 14 dropped (schema 0.2.0, 12 features). The rule was pre-registered, so this is a finding, not a patch.
5. **Detection-scope wording changed (approved by Bibek):** the system "detects fraud transactions of type TRANSFER and CASH_OUT as labelled by PaySim, which simulates account-takeover fund-draining; the two legs are not linked at the account level in the dataset (EDA gate G2), so the features do not model the chain." README abstract, objective 2 and section 10 updated to match.
6. **Base rates differ per split** (G6). Every reported metric states the prevalence of the split it was computed on.

**Still open:**
- `PROJECT_CONTEXT.md` says the replay pool is separate from Test because the two pipelines "compute features differently: online Redis state vs. batch dataframe". With D1 and D6 they compute them identically and can be reconciled exactly. The split stays as locked; only that justification needs rewording.

## Sources

- PaySim column descriptions (step = 1 hour, 744 steps, `isFlaggedFraud` rule, merchant note): [Medium, "Financial datasets for fraud detection"](https://medium.com/@lukewago/financial-datasets-for-fraud-detection-af20be29ffbc), a secondary reproduction of the Kaggle description.
- Distinct `nameOrig` count (6,353,307), fraud only on `TRANSFER`/`CASH_OUT`, no merchant recipients in those types: [Logistic regression on payment data (notebook)](https://sebastian-qr.github.io/Logistic_regression_creditcardpayments.html). Third-party, single source: gates G1, G4 and G6 exist to confirm it.
- Dataset: [PaySim on Kaggle](https://www.kaggle.com/datasets/ealaxi/paysim1). FIU-Nepal red flags: as recorded in README sections 2 and 3.

---

## Appendix A — `shared/features/core.py`

```python
"""shared/features/core.py - the ONE feature function (docs/FEATURE_SPEC.md).

Imported identically by the training notebooks, the Flow A fraud consumer and
core-api's Flow C batch path. Nobody re-implements any of this.

Structural leakage guard: compute_features() is read-only and sees only state
built from EARLIER events; update_dest_state() runs AFTER scoring. The event
model has no label field, so isFraud cannot reach the features.

Schema 0.2.0: the origin-side "inbound transfer" features were dropped after EDA
gate G2 (no fraud cash-out follows an inbound transfer to the same account in the
training split). State is now read for the RECIPIENT only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

FEATURE_SCHEMA_VERSION = "0.2.0"  # draft; becomes 1.0.0 after the real-data parity run (S1-09)


@dataclass(frozen=True)
class FeatureConfig:
    window_steps: int = 24  # PaySim: 1 step = 1 hour, so 24 steps = one day
    ratio_clip: float = 10.0  # upper bound for ratio features (linear-model stability)


CONFIG = FeatureConfig()

# Scope: PaySim's fraud label appears only on these two types. Only these are scored.
SCORED_TYPES = frozenset({"TRANSFER", "CASH_OUT"})

FEATURE_NAMES: tuple[str, ...] = (
    # stateless, from the current row
    "type_is_transfer",
    "log_amount",
    "log_orig_balance_before",
    "amount_to_orig_balance",
    "orig_balance_zero",
    "orig_drained",
    # balance-consistency group (simulator-artefact risk, ablation required)
    "orig_balance_error",
    "dest_balance_error",
    "dest_old_balance_zero",
    "dest_new_balance_zero",
    # stateful, recipient side
    "dest_inbound_transfer_count_24h",
    "dest_has_prior_inbound_transfer",
)

BALANCE_CONSISTENCY_GROUP = (
    "orig_balance_error",
    "dest_balance_error",
    "dest_old_balance_zero",
    "dest_new_balance_zero",
)

PAYSIM_COLUMN_MAP = {
    "step": "step",
    "type": "type",
    "amount": "amount",
    "nameOrig": "name_orig",
    "oldbalanceOrg": "oldbalance_org",
    "newbalanceOrig": "newbalance_orig",
    "nameDest": "name_dest",
    "oldbalanceDest": "oldbalance_dest",
    "newbalanceDest": "newbalance_dest",
}  # isFraud and isFlaggedFraud are deliberately absent


class TransactionEvent(BaseModel):
    """One transaction as the feature function sees it. No label field, by design."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step: int = Field(ge=0)
    type: Literal["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]
    amount: float = Field(ge=0, allow_inf_nan=False)
    name_orig: str = Field(min_length=1)
    oldbalance_org: float = Field(allow_inf_nan=False)
    newbalance_orig: float = Field(allow_inf_nan=False)
    name_dest: str = Field(min_length=1)
    oldbalance_dest: float = Field(allow_inf_nan=False)
    newbalance_dest: float = Field(allow_inf_nan=False)


@dataclass(frozen=True)
class AccountState:
    """Per-account memory: TRANSFER credits received inside the window + a lifetime count."""

    inbound: tuple[tuple[int, float], ...] = ()  # (step, amount), oldest first
    inbound_total: int = 0  # lifetime count of inbound TRANSFERs, never pruned


EMPTY_STATE = AccountState()


class StateStore(Protocol):
    def get(self, name: str) -> AccountState: ...  # EMPTY_STATE if unknown; must not create
    def put(self, name: str, state: AccountState) -> None: ...


class DictStore:
    """In-memory store: training, tests, Flow C."""

    def __init__(self) -> None:
        self.data: dict[str, AccountState] = {}

    def get(self, name: str) -> AccountState:
        return self.data.get(name, EMPTY_STATE)

    def put(self, name: str, state: AccountState) -> None:
        self.data[name] = state


def _log1p_nonneg(x: float) -> float:
    return math.log1p(max(x, 0.0))


def _signed_log1p(x: float) -> float:
    return math.copysign(math.log1p(abs(x)), x)


def _in_window(state: AccountState, step: int, window: int) -> list[tuple[int, float]]:
    return [(s, a) for s, a in state.inbound if step - s < window]


def compute_features(
    e: TransactionEvent,
    dest: AccountState,
    cfg: FeatureConfig = CONFIG,
) -> dict[str, float]:
    """Read-only. `dest` is the RECIPIENT's state BEFORE this event. Scored types only."""
    if e.type not in SCORED_TYPES:
        raise ValueError(f"type {e.type!r} is out of detection scope; do not score it")

    d_count = len(_in_window(dest, e.step, cfg.window_steps))

    def ratio(num: float, den: float) -> float:
        return min(num / den, cfg.ratio_clip) if den > 0 else 0.0

    values = {
        "type_is_transfer": 1.0 if e.type == "TRANSFER" else 0.0,
        "log_amount": _log1p_nonneg(e.amount),
        "log_orig_balance_before": _log1p_nonneg(e.oldbalance_org),
        "amount_to_orig_balance": ratio(e.amount, e.oldbalance_org),
        "orig_balance_zero": 1.0 if e.oldbalance_org == 0 else 0.0,
        "orig_drained": 1.0 if (e.oldbalance_org > 0 and e.newbalance_orig == 0) else 0.0,
        "orig_balance_error": _signed_log1p(e.oldbalance_org - e.amount - e.newbalance_orig),
        "dest_balance_error": _signed_log1p(e.oldbalance_dest + e.amount - e.newbalance_dest),
        "dest_old_balance_zero": 1.0 if e.oldbalance_dest == 0 else 0.0,
        "dest_new_balance_zero": 1.0 if e.newbalance_dest == 0 else 0.0,
        "dest_inbound_transfer_count_24h": float(d_count),
        "dest_has_prior_inbound_transfer": 1.0 if dest.inbound_total > 0 else 0.0,
    }
    return {name: values[name] for name in FEATURE_NAMES}  # fixed order


def update_dest_state(
    e: TransactionEvent, dest: AccountState, cfg: FeatureConfig = CONFIG
) -> AccountState:
    """State AFTER the event. Only a TRANSFER changes anything (credit to the recipient)."""
    if e.type != "TRANSFER":
        return dest
    kept = tuple((s, a) for s, a in dest.inbound if e.step - s < cfg.window_steps)
    return AccountState(inbound=kept + ((e.step, e.amount),), inbound_total=dest.inbound_total + 1)


def process_event(
    e: TransactionEvent, store: StateStore, cfg: FeatureConfig = CONFIG
) -> dict[str, float] | None:
    """Score-then-update. Returns features for scored types, else None.

    Used verbatim by the training pass and Flow C. The Flow A worker calls
    compute_features() and update_dest_state() separately (see FEATURE_SPEC section 5).
    """
    dest = store.get(e.name_dest)  # read BEFORE the update, so a transfer never sees its own credit
    features = compute_features(e, dest, cfg) if e.type in SCORED_TYPES else None
    new_dest = update_dest_state(e, dest, cfg)
    if new_dest is not dest:
        store.put(e.name_dest, new_dest)
    return features
```

## Appendix B — `shared/features/batch.py`

```python
"""shared/features/batch.py - sequential driver for training and Flow C.

Runs the same process_event() the streaming consumer runs, in row order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .core import (
    CONFIG,
    FEATURE_NAMES,
    PAYSIM_COLUMN_MAP,
    DictStore,
    FeatureConfig,
    StateStore,
    TransactionEvent,
    process_event,
)

if TYPE_CHECKING:
    import pandas as pd


def build_feature_table(
    df: "pd.DataFrame",
    store: StateStore | None = None,
    cfg: FeatureConfig = CONFIG,
    validate: bool = True,
) -> tuple["pd.DataFrame", StateStore]:
    """Features for every scored row of `df`, in ONE chronological pass.

    `df` must hold the PaySim columns in PAYSIM_COLUMN_MAP, in processing order
    (the original CSV order, `step` non-decreasing). Returns a frame indexed by
    the original row index (scored rows only) and the final store, so the ETL can
    snapshot state at the replay-pool boundary.

    validate=False builds events with model_construct (trusted Parquet path only);
    stream, API and upload ingress always validate.
    """
    import pandas as pd  # local import: core.py stays pandas-free for the workers

    missing = [c for c in PAYSIM_COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"missing PaySim columns: {missing}")
    if not df["step"].is_monotonic_increasing:  # non-decreasing
        raise ValueError("rows must be in chronological order (step non-decreasing)")

    store = store if store is not None else DictStore()
    make = TransactionEvent if validate else TransactionEvent.model_construct
    src = list(PAYSIM_COLUMN_MAP)
    dst = [PAYSIM_COLUMN_MAP[c] for c in src]

    index: list = []
    rows: list[list[float]] = []
    for idx, *vals in df[src].itertuples(name=None):
        event = make(**dict(zip(dst, vals)))
        feats = process_event(event, store, cfg)
        if feats is not None:
            index.append(idx)
            rows.append(list(feats.values()))
    return pd.DataFrame(rows, index=pd.Index(index), columns=list(FEATURE_NAMES)), store
```

`shared/features/__init__.py` re-exports the names used in section 5. The tests are in `tests/test_features.py` (included in the code bundle).
